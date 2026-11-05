"""Medical lecture transcript correction & slide-evidence helpers.

Separate specialist term restoration from slide alignment.
Never alter the saved speech-recognition original.
"""
from __future__ import annotations
import re
from collections import Counter

WORD = re.compile(r"(?<![A-Za-z0-9])(?:\d{1,3}[-–])?[A-Za-z][A-Za-z0-9αβγεδ+/-]{2,}")
KO = re.compile(r"[가-힣]{2,}")
NUM = re.compile(r"\d+(?:\.\d+)?%?")
SKIP = {
    "the", "and", "that", "with", "from", "this", "which", "were", "have",
    "there", "these", "those", "than", "only", "more", "most", "some",
    "into", "your", "their", "between", "after", "before", "image",
    "copyright", "figure", "table", "page", "slide", "chapter",
    "lecture", "summary", "data", "university", "source", "normal",
    "patient", "patients", "clinical", "medical", "study", "result",
    "results", "treatment", "diagnosis", "class", "note", "review",
}


def glossary_from_pdf(pages: list[dict], max_chars: int = 3800) -> str:
    """Extract *actual* scientific English tokens from all PDF pages."""
    counts = Counter()
    for p in pages:
        for word in WORD.findall((p.get("text") or "")[:13000]):
            word = word.strip("-/")
            if len(word) > 55 or word.casefold() in SKIP:
                continue
            counts[word] += 1
    words = sorted(
        counts, key=lambda x: (
            -counts[x] - (2 if any(c.isdigit() for c in x) else 0),
            x.lower(),
        )
    )
    text = []
    for item in words:
        if len(", ".join(text + [item])) > max_chars:
            break
        text.append(item)
    return ", ".join(text)


def correction_prompt(batch: list[dict], glossary: str,
                      context_before: str, context_after: str, json_payload: str) -> str:
    return (
        "당신은 한국 의과대학 교수의 구어체 강의 전사를 교정하는 의료 전문 에디터다. "
        "이번 요청에서는 PDF 페이지 매칭이나 요약을 절대 하지 않는다. "
        'JSON 객체 {"items":[{"id":"T0001","corrected":"전체 교정문",'
        '"terms":[{"from":"원문","to":"수정 용어","basis":"PDF|의학 맥락"}]}]}만 반환한다.\n'
        "핵심: 한국어로 음차되거나 STT가 엉뚱한 한국어로 인식한 영문 "
        "의학용어·약물·유전자·효소·수용체·검사명은 앞뒤 맥락과 PDF 용어집에 "
        "대조하여 표준 영문 표기로 바로잡는다. 영어를 한글로 음차해 둔 것을 "
        "그대로 방치하지 말 것. 예: '에스지엘티 투'→'SGLT2', "
        "'알도스테론'→'aldosterone', '페오크로모사이토마'→"
        "'pheochromocytoma', '에이씨티에이치'→'ACTH'. "
        "예시는 실제 발언이 아니므로 무조건 삽입하지 않는다.\n"
        "의학적으로 서로 다른 용어가 가능한 경우 소리/맥락/PDF에 근거가 "
        "충분할 때만 고치고, 추측으로 내용을 만들어내지 말 것. "
        "원문에 있는 수치(단위 포함), 부정, 비교, 사례, 질문, 교수님의 반복된 "
        "강조, 주장·의견·순서는 모두 보존한다. 문장을 요약하거나 "
        "새로운 의학 지식을 더하지 않는다. "
        "단, 의미가 없는 단독 말버릇과 머뭇거림 '어', '음', '어어', "
        "'그...' 등은 자연스럽게 정리한다. "
        "'그런데', '그러면', '그렇죠', '어떤', 부정 표현, 실제 질문은 삭제하지 않는다. "
        "의미를 가지는 반복(강조)은 삭제하지 않는다.\n"
        "각 입력 블록의 id를 정확히 1번씩 반환한다. "
        "정답 확인이 안 되는 의학용어는 억지로 바꾸지 않는다. "
        "영어로 바꾼 용어는 terms에 변경 전후를 적는다.\n"
        f"이전 문맥(수정하지 말 것): {context_before[-700:]}\n"
        f"다음 문맥(수정하지 말 것): {context_after[:500]}\n"
        f"해당 강의 PDF에서 직접 추출한 참고 영문 용어집: {glossary}\n"
        f"전사 원문(JSON): {json_payload}"
    )


def shortlist_pages(text: str, pages: list[dict], last_page: int | None,
                    limit: int = 14) -> list[dict]:
    """Select plausible PDF pages using content evidence and time continuity."""
    words = set(x.casefold() for x in WORD.findall(text))
    # Korean substrings can help, but avoid flooding score with common words.
    words.update(x for x in KO.findall(text) if len(x) > 2)
    ranking = []
    for page in pages:
        n = int(page["page"])
        body = page.get("text") or ""
        lower = body.casefold()
        hit = [w for w in words if w in lower and len(w) >= 3]
        score = sum(min(4, len(x) / 3) for x in hit)
        if last_page is not None:
            score += 2.8 / (1 + abs(n - last_page))
        ranking.append((score, n, hit, body))
    if not ranking:
        return []
    chosen = sorted(ranking, key=lambda x: (-x[0], x[1]))[:max(1, limit - 2)]
    keep = {n: (hits, body) for _, n, hits, body in chosen}
    if last_page is not None:
        for _, n, hits, body in ranking:
            if abs(n - last_page) <= 1:
                keep[n] = (hits, body)
    else:
        for _, n, hits, body in ranking[:2]:
            keep[n] = (hits, body)
    result = []
    for n in sorted(keep)[:limit]:
        hits, body = keep[n]
        extracts = [body[:500]]
        for token in sorted(hits, key=len, reverse=True)[:4]:
            i = body.casefold().find(token)
            if i >= 500:
                extracts.append(body[max(0, i - 110):i + 240])
        result.append({"page": n, "evidence": "\n...\n".join(extracts)[:1550]})
    return result


def alignment_prompt(batch: list[dict], candidate_pages: list[dict],
                     last_page: int | None) -> str:
    import json
    return (
        "의과대학 강의의 '실제 PDF 원본 페이지'만 대조하여 정렬하라. "
        "전사문 교정은 이미 끝났다. 교정문을 수정하거나 줄이지 마라.\n"
        'JSON {"items":[{"id":"T0001","page":1 또는 null,'
        '"confidence":0.0~1.0,"reason":"PDF에 실제로 존재하는 대응 근거"}]}.\n'
        "입력의 모든 id를 정확히 1번씩 반환한다. 반드시 후보 페이지 "
        "중에서만 선택하라. PDF와 무관한 언급이나 그림만으로 추정이 "
        "불가한 경우 page=null로 반환하라. 없는 근거를 지어내지 마라. "
        "페이지는 반드시 PDF 실제 페이지 번호(1부터 시작). "
        "강의 순서가 앞뒤로 움직일 수 있다. "
        f"참고: 직전 매칭 페이지={last_page}.\n"
        "페이지 후보 및 텍스트: "
        + json.dumps(candidate_pages, ensure_ascii=False) +
        "\n교정된 발언들: " +
        json.dumps([{"id": b["id"], "text": b["corrected"]} for b in batch], ensure_ascii=False)
    )


def correction_warning(raw: str, corrected: str) -> str | None:
    if not corrected.strip():
        return "교정문이 비어 있음"
    nums = NUM.findall(raw)
    missing = [x for x in nums if x not in corrected]
    if missing:
        return "수치 변경 또는 누락 의심: " + ", ".join(missing[:8])
    if len(raw.strip()) >= 80 and len(corrected.strip()) < len(raw.strip()) * .60:
        return "과도한 발언 축약 의심"
    return None
