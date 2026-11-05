"""Cloudflare Workers AI Whisper Large V3 Turbo REST client.

Runs server-side only. Never expose account IDs or API tokens in the browser.
Official endpoint:
POST /client/v4/accounts/{account_id}/ai/run/@cf/openai/whisper-large-v3-turbo
"""
from __future__ import annotations
import base64
import json
import os
import random
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MODEL = "@cf/openai/whisper-large-v3-turbo"
API_BASE = "https://api.cloudflare.com/client/v4/accounts"
TRANSIENT = {408, 429, 500, 502, 503, 504}


def configured() -> bool:
    return bool(os.getenv("CLOUDFLARE_ACCOUNT_ID") and os.getenv("CLOUDFLARE_API_TOKEN"))


def build_medical_prompt(pages: list[dict], max_chars: int = 1100) -> str:
    """Extract English/Latin scientific terms directly from the supplied PDF.

    Vocabulary is *hint only*, not a forced transcription or model fine-tuning.
    Avoid injecting every English stopword and repeated sentence as context.
    """
    frequencies: dict[str, int] = {}
    for page in pages:
        text = (page.get("text") or "")[:13000]
        tokens = re.findall(
            r"(?<![A-Za-z])(?:[A-Za-z][A-Za-z0-9]*)(?:[-_/][A-Za-z0-9]+){0,3}(?![A-Za-z])",
            text,
        )
        for term in tokens:
            if len(term) < 4 or len(term) > 55:
                continue
            if term.lower() in {
                "with", "from", "have", "this", "that", "these", "those",
                "patients", "because", "study", "figure", "table", "lecture",
                "page", "normal", "clinical", "results", "between", "into",
                "increase", "decrease", "diagnosis", "treatment", "human",
            }:
                continue
            frequencies[term] = frequencies.get(term, 0) + 1
    if not frequencies:
        return ""
    # Frequent specialized vocabulary first; limit to avoid drowning Whisper.
    terms = sorted(frequencies, key=lambda t: (-frequencies[t], t.lower()))
    head = "한국어 의학 강의입니다. 다음 강의록의 의학용어와 약물명을 정확히 들리는 대로 전사하세요: "
    tail = []
    for term in terms[:130]:
        joined = head + ", ".join(tail + [term])
        if len(joined) > max_chars:
            break
        tail.append(term)
    return head + ", ".join(tail) if tail else ""


def parse_whisper_result(payload: dict, *, chunk_number: int,
                         start: float, end: float) -> dict:
    """Normalize Cloudflare API response and retain every returned segment."""
    if not isinstance(payload, dict):
        raise RuntimeError("Cloudflare가 올바른 JSON 객체를 반환하지 않았습니다.")
    if payload.get("success") is False:
        err = payload.get("errors", [])
        raise RuntimeError("Cloudflare Workers AI 실패: " + json.dumps(err, ensure_ascii=False)[:500])
    body = payload.get("result", payload)
    if not isinstance(body, dict):
        raise RuntimeError("Cloudflare 전사 결과 형식이 올바르지 않습니다.")
    raw_segments = body.get("segments") or []
    segments = []
    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            words = item.get("text")
            if not isinstance(words, str) or not words.strip():
                continue
            try:
                a = float(item.get("start", 0))
                b = float(item.get("end", end - start))
            except (TypeError, ValueError):
                a, b = 0.0, end - start
            a = max(0.0, min(end - start, a))
            b = max(a, min(end - start, b))
            segments.append({
                "text": words.strip(),
                "start": round(start + a, 2),
                "end": round(start + b, 2),
                "chunk": chunk_number + 1,
            })
    if not segments:
        full = body.get("text", "")
        if not isinstance(full, str) or not full.strip():
            raise RuntimeError(
                f"Cloudflare Whisper {chunk_number + 1}번 구간에서 전사 텍스트가 비어 있습니다."
            )
        # Cloudflare may omit segment timestamps; preserve text, flag timing
        # as an estimate instead of inventing precise timing.
        segments = [{
            "text": full.strip(), "start": round(start, 2),
            "end": round(end, 2), "chunk": chunk_number + 1,
            "timing_estimated": True,
        }]
    return {
        "number": chunk_number, "start": start, "end": end,
        "segments": segments, "model": MODEL,
        "language": (body.get("transcription_info") or {}).get("language"),
    }


def transcribe_cloudflare_chunk(*, chunk: dict, job_id: str, bucket_blob,
                                prompt: str = "", emit=lambda msg: None) -> dict:
    """Call Cloudflare once per 60-sec audio chunk, with private GCS caching.

    bucket_blob takes a *relative object key* and returns a GCS blob.
    Reuses completed chunks on retries, without billing for duplicate calls.
    """
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        raise RuntimeError(
            "Cloudflare Whisper 사용 준비가 안 됐어요. "
            "Cloud Run에 CLOUDFLARE_ACCOUNT_ID와 CLOUDFLARE_API_TOKEN을 설정해 주세요."
        )
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account_id):
        raise RuntimeError("Cloudflare Account ID는 32자리 영숫자(16진수)여야 합니다.")
    number = chunk["number"]
    key = f"jobs/{job_id}/cache/cf_whisper_{number:04d}.json"
    blob = bucket_blob(key)
    if blob.exists():
        cached = json.loads(blob.download_as_text(encoding="utf-8"))
        if cached.get("model") == MODEL and cached.get("prompt") == prompt:
            return cached["result"]
    path = Path(chunk["path"])
    audio_bytes = path.read_bytes()
    if len(audio_bytes) > 10_000_000:
        raise RuntimeError(f"Whisper {number + 1}번 오디오 구간이 너무 큽니다. 더 짧게 분할해야 합니다.")
    request_body = {
        "audio": base64.b64encode(audio_bytes).decode("ascii"),
        "task": "transcribe",
        "language": "ko",
        "vad_filter": False,  # prioritize preserving lecturer speech
    }
    if prompt:
        request_body["initial_prompt"] = prompt
    url = f"{API_BASE}/{account_id}/ai/run/{MODEL}"
    data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    response = None
    for attempt in range(3):
        req = Request(
            url,
            data=data,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=180) as r:
                response = json.loads(r.read().decode("utf-8"))
            break
        except HTTPError as exc:
            details = exc.read(1000).decode("utf-8", errors="replace")
            if exc.code in TRANSIENT and attempt < 2:
                emit(f"Cloudflare Whisper {number + 1}번 구간: HTTP {exc.code}, 자동 재시도")
                time.sleep([4, 12][attempt] + random.random() * 2)
                continue
            raise RuntimeError(
                f"Cloudflare Whisper HTTP {exc.code}: {details[:450]}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            if attempt >= 2:
                raise RuntimeError(f"Cloudflare 네트워크 연결 실패: {exc}") from exc
            time.sleep([4, 12][attempt] + random.random() * 2)
    if response is None:
        raise RuntimeError("Cloudflare Whisper 응답이 없습니다.")
    result = parse_whisper_result(
        response, chunk_number=number, start=chunk["start"], end=chunk["end"]
    )
    blob.upload_from_string(
        json.dumps({"model": MODEL, "prompt": prompt, "result": result},
                   ensure_ascii=False),
        content_type="application/json",
    )
    return result
