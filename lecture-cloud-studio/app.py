"""Lecture Cloud Studio — private-by-password Google Cloud lecture workflow.

Uploads go directly to a private Cloud Storage bucket (not through Cloud Run's 32 MB
HTTP request limit). Each audio is cut into <= 18-minute FLAC chunks before Chirp 3.
Original transcripts remain untouched; all AI revisions are separate.
"""
from __future__ import annotations

import asyncio
import difflib
import hmac
import json
import os
import queue
import re
import secrets
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import fitz
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from google.api_core.client_options import ClientOptions
from google.cloud import storage
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from google import genai
from google.genai import types
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or ""
BUCKET = os.getenv("GCS_BUCKET", "")
SPEECH_REGION = os.getenv("SPEECH_REGION", "us")
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "chirp_3")
GEMINI_REGION = os.getenv("GEMINI_REGION", "global")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
SECRET = os.getenv("SESSION_SECRET", "")
CHUNK_SECONDS = 18 * 60
OVERLAP_SECONDS = 8
app = FastAPI(title="Lecture Cloud Studio", docs_url=None, redoc_url=None)
active_jobs: set[str] = set()
active_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def storage_client():
    if not BUCKET:
        raise RuntimeError("GCS_BUCKET 환경변수가 설정되지 않았습니다.")
    return storage.Client(project=PROJECT or None)


def object_blob(name: str):
    return storage_client().bucket(BUCKET).blob(name)


def save_json(name: str, obj: dict):
    object_blob(name).upload_from_string(
        json.dumps(obj, ensure_ascii=False), content_type="application/json"
    )


def load_json(name: str):
    blob = object_blob(name)
    if not blob.exists():
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return json.loads(blob.download_as_text(encoding="utf-8"))


def job_path(job_id: str, leaf: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise HTTPException(400, "잘못된 작업 ID")
    return f"jobs/{job_id}/{leaf}"


def meta_path(job_id: str) -> str:
    return job_path(job_id, "meta.json")


def result_path(job_id: str) -> str:
    return job_path(job_id, "result.json")


def auth_check(request: Request):
    if not APP_PASSWORD or not SECRET:
        raise HTTPException(503, "APP_PASSWORD와 SESSION_SECRET을 서버에 설정하세요.")
    cookie = request.cookies.get("lecture_session", "")
    try:
        payload = URLSafeTimedSerializer(SECRET).loads(cookie, max_age=7 * 86400)
        if payload != "signed-in":
            raise BadSignature("Invalid session")
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "로그인이 필요합니다.")


def gclient():
    if not PROJECT:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT 환경변수가 필요합니다.")
    return genai.Client(vertexai=True, project=PROJECT, location=GEMINI_REGION)


def gemini_json(prompt: str) -> dict:
    res = gclient().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
            max_output_tokens=8192,
        ),
    )
    if not res.text:
        raise RuntimeError("Gemini가 빈 결과를 반환했습니다.")
    return json.loads(res.text)


def split_text_preserving(text: str, max_chars: int = 650) -> list[str]:
    """Split without deleting any words; whitespace at boundaries is not substantive."""
    source = text.strip()
    if not source:
        return []
    pieces = re.split(r"(?<=[.!?。])\s+|(?<=\n)\s*", source)
    pieces = [p.strip() for p in pieces if p.strip()]
    out, current = [], ""
    for piece in pieces:
        if len(current) + len(piece) + 1 > max_chars and current:
            out.append(current)
            current = ""
        while len(piece) > max_chars:
            # Prefer a word boundary to avoid chopping terminology.
            idx = piece.rfind(" ", 0, max_chars)
            if idx < max_chars // 2:
                idx = max_chars
            if current:
                out.append(current)
                current = ""
            out.append(piece[:idx].strip())
            piece = piece[idx:].strip()
        current = (current + " " + piece).strip() if current else piece
    if current:
        out.append(current)
    return out


def duration_seconds(file: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(file)],
        text=True, timeout=60,
    ).strip()
    return float(out)


def make_chunks(audio: Path, folder: Path):
    duration = duration_seconds(audio)
    if duration <= 0:
        raise ValueError("오디오 길이를 읽을 수 없습니다.")
    chunks = []
    start = 0.0
    i = 0
    while start < duration - 0.05:
        end = min(duration, start + CHUNK_SECONDS)
        path = folder / f"chunk_{i:03}.flac"
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{start:.3f}", "-i", str(audio),
            "-t", f"{end - start:.3f}", "-vn",
            "-ac", "1", "-ar", "16000", "-c:a", "flac", str(path),
        ]
        subprocess.run(cmd, check=True, timeout=240)
        if not path.exists() or path.stat().st_size < 1000:
            raise RuntimeError(f"오디오 분할 실패: {i + 1}번")
        chunks.append({"number": i, "start": round(start, 2),
                       "end": round(end, 2), "path": path})
        if end >= duration - 0.05:
            break
        start = end - OVERLAP_SECONDS
        i += 1
    return duration, chunks


def secs(value) -> float:
    return float(getattr(value, "seconds", 0) or 0) + float(
        getattr(value, "nanos", 0) or 0
    ) / 1e9


def transcribe_chunk(job_id: str, chunk: dict) -> dict:
    number = chunk["number"]
    saved = job_path(job_id, f"cache/stt_{number:03}.json")
    blob = object_blob(saved)
    if blob.exists():
        return json.loads(blob.download_as_text(encoding="utf-8"))
    gcs_key = job_path(job_id, f"chunks/{number:03}.flac")
    gcs_blob = object_blob(gcs_key)
    if not gcs_blob.exists():
        gcs_blob.upload_from_filename(str(chunk["path"]), content_type="audio/flac")
    uri = f"gs://{BUCKET}/{gcs_key}"
    client = SpeechClient(client_options=ClientOptions(
        api_endpoint=f"{SPEECH_REGION}-speech.googleapis.com"
    ))
    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=["ko-KR"],
        model=SPEECH_MODEL,
    )
    req = cloud_speech.BatchRecognizeRequest(
        recognizer=f"projects/{PROJECT}/locations/{SPEECH_REGION}/recognizers/_",
        config=config,
        files=[cloud_speech.BatchRecognizeFileMetadata(uri=uri)],
        recognition_output_config=cloud_speech.RecognitionOutputConfig(
            inline_response_config=cloud_speech.InlineOutputConfig()
        ),
    )
    operation = client.batch_recognize(request=req)
    response = operation.result(timeout=1800)
    entry = response.results.get(uri)
    if entry is None or not entry.transcript.results:
        raise RuntimeError(f"{number+1}번 음성 구간에서 전사 결과가 반환되지 않았습니다.")
    segments = []
    prev_end = 0.0
    for res in entry.transcript.results:
        if not res.alternatives:
            continue
        text = res.alternatives[0].transcript.strip()
        if not text:
            continue
        segment_end = secs(res.result_end_offset) or chunk["end"] - chunk["start"]
        segment_end = max(prev_end, segment_end)
        subdivisions = split_text_preserving(text)
        total = max(1, sum(len(x) for x in subdivisions))
        cursor = prev_end
        for part in subdivisions:
            part_end = cursor + (segment_end - prev_end) * len(part) / total
            segments.append({"text": part, "start": round(chunk["start"] + cursor, 2),
                             "end": round(chunk["start"] + part_end, 2),
                             "chunk": number + 1})
            cursor = part_end
        prev_end = segment_end
    result = {"number": number, "start": chunk["start"], "end": chunk["end"],
              "segments": segments}
    if not segments:
        raise RuntimeError(f"{number+1}번 구간의 전사문이 비어 있습니다.")
    save_json(saved, result)
    return result


def extract_pdf(pdf: Path) -> list[dict]:
    pages = []
    with fitz.open(str(pdf)) as doc:
        for i, page in enumerate(doc):
            txt = re.sub(r"\s+", " ", page.get_text(sort=True)).strip()
            pages.append({"page": i + 1, "text": txt[:13000],
                          "text_length": len(txt),
                          "needs_visual_review": len(txt) < 45})
    return pages


def get_original_blocks(text: str):
    blocks = []
    parts = [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]
    for para in parts:
        for item in split_text_preserving(para):
            blocks.append({"id": f"T{len(blocks)+1:04d}", "raw": item,
                           "corrected": item, "page": None, "confidence": 0.0,
                           "start": None, "end": None, "chunk": None, "flags": []})
    return blocks


def get_audio_blocks(chunk_results: list[dict]):
    blocks = []
    # Preserve overlapping speech rather than deleting uncertain words.
    for group in sorted(chunk_results, key=lambda z: z["number"]):
        for s in group["segments"]:
            blocks.append({"id": f"T{len(blocks)+1:04d}", "raw": s["text"],
                           "corrected": s["text"], "page": None, "confidence": 0.0,
                           "start": s["start"], "end": s["end"], "chunk": s["chunk"],
                           "flags": []})
    # Border duplicates are *flagged*, not automatically removed.
    for i in range(1, len(blocks)):
        a, b = blocks[i-1], blocks[i]
        if a["chunk"] != b["chunk"] and a["end"] and b["start"] is not None:
            if b["start"] < a["end"]:
                b["flags"].append("분할 경계 중복 가능: 원문 보존")
    return blocks


def compare_correction(raw: str, corrected: str) -> list[str]:
    warnings = []
    if not corrected.strip():
        return ["교정문 비어 있음"]
    ratio = len(corrected.strip()) / max(len(raw.strip()), 1)
    if ratio < 0.72:
        warnings.append("원문 대비 교정문 축약 의심")
    if ratio > 1.75:
        warnings.append("원문 대비 교정문 확장 의심")
    nums = re.findall(r"\d+(?:\.\d+)?%?", raw)
    missed = [n for n in nums if n not in corrected]
    if missed:
        warnings.append("숫자 변경/누락 확인: " + ", ".join(missed[:10]))
    return warnings


def correct_blocks(blocks: list[dict], pages: list[dict], emit):
    if not blocks:
        return blocks
    outline = "\n".join(
        f"p{p['page']}: {(p['text'] or '[그림/텍스트 없음]')[:190]}"
        for p in pages
    )
    if len(outline) > 26000:
        outline = outline[:26000]
    prior = 1
    for base in range(0, len(blocks), 6):
        batch = blocks[base:base+6]
        payload = json.dumps([{"id": b["id"], "raw": b["raw"]} for b in batch],
                             ensure_ascii=False)
        prompt = (
            "당신은 의과대학 강의 전사 교정기다. JSON 객체 {\"items\": [...]}만 반환한다.\n"
            "중요: 원문을 요약, 재서술, 축약, 확장하지 않는다. 발언의 사례, 수치, "
            "질문, 반복 강조를 모두 보존한다. 명백한 오인식 및 의학용어만 수정한다. "
            "원문에서 들리지 않은 사실을 추가하지 않는다.\n"
            "각 입력 ID에 대해 반드시 한 항목을 반환하며 순서를 유지한다.\n"
            "각 항목: {\"id\":\"T0001\",\"corrected\":\"교정문\","
            "\"page\":1 또는 null,\"confidence\":0.0~1.0,\"reason\":\"매칭 근거\"}.\n"
            "페이지는 아래 원본 PDF 페이지 목차와 실제 발언을 대조한다. "
            "불확실하거나 그림에만 내용이 있는 경우 null을 반환한다. "
            f"직전 페이지 참고값: {prior}. 교수는 페이지를 되돌아갈 수 있다.\n\n"
            "PDF 페이지 색인:\n"+outline+"\n\n원문 블록:\n"+payload
        )
        error = None
        items = None
        for attempt in range(2):
            try:
                response = gemini_json(prompt)
                candidates = response.get("items", [])
                found = {c.get("id"): c for c in candidates if isinstance(c, dict)}
                if any(b["id"] not in found for b in batch):
                    raise ValueError("일부 원문 ID 누락")
                items = found
                break
            except Exception as exc:
                error = str(exc)
        for block in batch:
            if items is None:
                block["flags"].append("AI 교정 실패: 원문 유지 / " + str(error)[:120])
                continue
            item = items[block["id"]]
            value = item.get("corrected")
            if not isinstance(value, str) or not value.strip():
                block["flags"].append("AI 교정문 누락: 원문 유지")
                continue
            block["corrected"] = value
            proposed = item.get("page")
            try:
                proposed = int(proposed) if proposed is not None else None
            except (TypeError, ValueError):
                proposed = None
            if proposed is not None and not (1 <= proposed <= len(pages)):
                proposed = None
            block["page"] = proposed
            try:
                block["confidence"] = max(0, min(1, float(item.get("confidence") or 0)))
            except (TypeError, ValueError):
                block["confidence"] = 0
            if block["confidence"] < 0.7 and proposed is not None:
                block["flags"].append("PDF 페이지 수동 확인 권장")
            if proposed is not None:
                prior = proposed
            block["flags"].extend(compare_correction(block["raw"], value))
        emit(f"교정·페이지 매칭: {min(base+len(batch),len(blocks))}/{len(blocks)} 문단")


def build_study(blocks: list[dict], pages: list[dict], emit):
    notes: dict[str, dict] = {}
    by_page: dict[int, list] = {}
    for b in blocks:
        if b["page"] is not None:
            by_page.setdefault(b["page"], []).append(b)
    for group_start in range(0, len(by_page), 5):
        nums = sorted(by_page)[group_start:group_start+5]
        data = []
        for n in nums:
            source = next((p for p in pages if p["page"] == n), None)
            data.append({
                "page": n,
                "slide": (source or {}).get("text", "")[:2600],
                "lecturer": [
                    {"id": b["id"], "text": b["corrected"]}
                    for b in by_page[n]
                ][:30],
            })
        try:
            response = gemini_json(
                "의과대학 강의 학습 노트를 작성해라. 입력에서만 근거를 가져온다. "
                "교수의 상세 발언에 집중하고, 한두 마디만 한 것은 간략히 한다. "
                "강의록에 없는 새 의학 내용을 임의로 추가하지 않는다. "
                "원문 발언과 슬라이드가 충돌하면 충돌 표시한다. "
                "JSON {\"pages\":[{\"page\":정수,\"note\":\"한국어 간결한 과외 설명\","
                "\"keypoints\":[\"핵심\"],\"source_ids\":[\"T0001\"]}]}.\n" +
                json.dumps(data, ensure_ascii=False)
            )
            for n in response.get("pages", []):
                if str(n.get("page", "")) in {str(x) for x in nums}:
                    notes[str(n["page"])] = n
        except Exception as exc:
            for n in nums:
                notes[str(n)] = {"page": n, "note": "",
                                  "keypoints": [], "source_ids": [],
                                  "error": str(exc)[:150]}
        emit(f"과외 노트: {min(group_start+len(nums),len(by_page))}/{len(by_page)} 페이지")
    return notes


def make_questions(notes: dict, emit):
    material = json.dumps(
        [{"page": int(p), "note": v.get("note", "")[:1200]}
         for p, v in list(notes.items())[:35] if v.get("note")],
        ensure_ascii=False
    )
    if not material or material == "[]":
        return []
    try:
        response = gemini_json(
            "다음 제공된 의학 강의 노트에만 근거하여, 이해를 점검하는 객관식 "
            "5문항을 만들어라. 실제 족보 문제가 아니므로 유형은 'AI 연습문제'다. "
            "모르면 억지로 만들지 않는다. JSON {\"questions\":["
            "{\"question\":\"문제\",\"choices\":[\"선지1\",\"선지2\",\"선지3\",\"선지4\"],"
            "\"answer\":0,\"explanation\":\"이유\",\"page\":1}]} "
            "answer는 0 기반 정답 번호다.\n"+material
        )
        arr = response.get("questions", [])
        validated = []
        for q in arr:
            if (isinstance(q, dict) and len(q.get("choices", [])) == 4
                    and isinstance(q.get("answer"), int)
                    and 0 <= q["answer"] <= 3):
                q["type"] = "AI 연습문제 (족보 아님)"
                validated.append(q)
        emit(f"AI 연습문제 {len(validated)}개 작성")
        return validated
    except Exception as exc:
        emit(f"문제 생성 보류: {str(exc)[:100]}")
        return []


def pipeline(job_id: str, emit):
    meta = load_json(meta_path(job_id))
    if not meta.get("files"):
        raise RuntimeError("업로드한 파일이 없습니다.")
    meta["stage"], meta["updated"] = "processing", now()
    save_json(meta_path(job_id), meta)
    with tempfile.TemporaryDirectory(prefix="lecture_") as td:
        folder = Path(td)
        files = meta["files"]
        local: dict[str, Path] = {}
        for kind, key in files.items():
            target = folder / (kind + Path(key).suffix.lower())
            object_blob(key).download_to_filename(str(target))
            local[kind] = target
        emit("업로드 파일 확인 완료")
        pdf_pages = extract_pdf(local["pdf"]) if "pdf" in local else []
        emit(f"PDF {len(pdf_pages)}페이지 분석 완료")
        reference = None
        if "txt" in local:
            reference = local["txt"].read_text(encoding="utf-8-sig", errors="replace")
        if "audio" in local:
            length, chunks = make_chunks(local["audio"], folder)
            emit(f"{length/60:.1f}분 오디오를 {len(chunks)}개 구간(각 18분 이하)으로 자동 분할")
            outputs = []
            # One by one avoids project quota bursts; each chunk is safely resumable.
            for i, chunk in enumerate(chunks):
                emit(f"음성인식 {i+1}/{len(chunks)} 구간 처리 중")
                outputs.append(transcribe_chunk(job_id, chunk))
                emit(f"음성인식 {i+1}/{len(chunks)} 구간 완료")
            blocks = get_audio_blocks(outputs)
            source_type = "chirp_3"
        else:
            blocks = get_original_blocks(reference or "")
            source_type = "clova_txt"
        if not blocks:
            raise RuntimeError("전사문이 비어 있습니다.")
        emit(f"원문 {len(blocks)}개 문단 저장")
        raw_snapshot = [{k: b[k] for k in ("id", "raw", "start", "end", "chunk")}
                        for b in blocks]
        # Never overwrite the original, even after manual corrections.
        save_json(job_path(job_id, "raw_blocks.json"), {"blocks": raw_snapshot})
        correct_blocks(blocks, pdf_pages, emit)
        source_ids = [x["id"] for x in raw_snapshot]
        out_ids = [x["id"] for x in blocks]
        flags = []
        if source_ids != out_ids:
            flags.append("원문 문단 ID 개수 또는 순서 불일치")
        flagged = sum(bool(b["flags"]) for b in blocks)
        matched = sum(b["page"] is not None for b in blocks)
        notes = {}
        questions = []
        if pdf_pages:
            notes = build_study(blocks, pdf_pages, emit)
            questions = make_questions(notes, emit)
        result = {
            "job_id": job_id, "source_type": source_type,
            "created": now(), "audio_length": length if "audio" in local else None,
            "blocks": blocks, "pages": pdf_pages, "notes": notes, "questions": questions,
            "clova_reference": reference if "audio" in local else None,
            "verification": {
                "input_blocks": len(source_ids), "output_blocks": len(out_ids),
                "all_ids_preserved": source_ids == out_ids,
                "matched_blocks": matched, "unmatched_blocks": len(blocks)-matched,
                "flagged_blocks": flagged, "warnings": flags,
                "note": "문단 ID 검증은 의미 누락 100% 보증이 아닙니다. 경고 문단을 직접 확인하세요.",
            },
        }
        save_json(result_path(job_id), result)
        meta["stage"] = "complete_with_warnings" if flagged or flags else "complete"
        meta["updated"] = now()
        save_json(meta_path(job_id), meta)
        emit("완료: 원본·교정본·페이지 매칭·과외 노트 저장")
        return result


class Login(BaseModel):
    password: str


class NewJob(BaseModel):
    title: str = Field(default="새 강의", max_length=160)


class UploadRequest(BaseModel):
    kind: str
    filename: str
    content_type: str
    size: int


class Ready(BaseModel):
    files: dict[str, str]


class BlockChange(BaseModel):
    id: str
    corrected: str | None = None
    page: int | None = None


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "configured": bool(PROJECT and BUCKET and APP_PASSWORD and SECRET)}


@app.post("/api/login")
def login(data: Login):
    if not APP_PASSWORD or not SECRET:
        raise HTTPException(503, "앱 비밀번호 환경변수를 먼저 설정하세요.")
    if not hmac.compare_digest(data.password, APP_PASSWORD):
        raise HTTPException(401, "비밀번호가 일치하지 않습니다.")
    token = URLSafeTimedSerializer(SECRET).dumps("signed-in")
    response = JSONResponse({"ok": True})
    response.set_cookie("lecture_session", token, httponly=True,
                        secure=os.getenv("COOKIE_SECURE", "true") == "true",
                        samesite="lax", max_age=7*86400)
    return response


@app.get("/api/me")
def me(request: Request):
    auth_check(request)
    return {"ok": True, "project": PROJECT, "bucket": BUCKET,
            "speech_model": SPEECH_MODEL, "speech_region": SPEECH_REGION,
            "gemini_model": GEMINI_MODEL}


@app.get("/api/jobs")
def list_jobs(request: Request):
    auth_check(request)
    rows = []
    for blob in storage_client().list_blobs(BUCKET, prefix="jobs/"):
        if blob.name.endswith("/meta.json"):
            try:
                rows.append(json.loads(blob.download_as_text(encoding="utf-8")))
            except Exception:
                continue
    return sorted(rows, key=lambda x: x.get("created", ""), reverse=True)[:80]


@app.post("/api/jobs")
def create_job(request: Request, data: NewJob):
    auth_check(request)
    job_id = uuid.uuid4().hex
    meta = {"id": job_id, "title": data.title.strip() or "새 강의",
            "created": now(), "updated": now(), "stage": "created", "files": {}}
    save_json(meta_path(job_id), meta)
    return meta


@app.post("/api/jobs/{job_id}/upload-session")
def upload_session(job_id: str, request: Request, data: UploadRequest):
    auth_check(request)
    meta = load_json(meta_path(job_id))
    if data.kind not in {"audio", "pdf", "txt", "questions"}:
        raise HTTPException(400, "지원하지 않는 업로드 종류입니다.")
    if data.size <= 0 or data.size > 1024 * 1024 * 1024:
        raise HTTPException(400, "1GB 이하의 파일을 업로드하세요.")
    extension = Path(data.filename).suffix.lower()
    allowed = {
        "audio": {".m4a", ".mp3", ".wav", ".flac", ".mp4", ".aac", ".ogg"},
        "pdf": {".pdf"}, "txt": {".txt"}, "questions": {".pdf"},
    }
    if extension not in allowed[data.kind]:
        raise HTTPException(400, f"{data.kind} 파일 형식을 확인하세요.")
    key = job_path(job_id, f"source/{data.kind}{extension}")
    blob = object_blob(key)
    mime = data.content_type or "application/octet-stream"
    # Cloud Run cannot take a 100MB upload in its normal HTTP request.
    # A resumable upload session lets the browser stream directly to private GCS.
    url = blob.create_resumable_upload_session(
        content_type=mime, size=data.size,
    )
    return {"upload_url": url, "object": key, "size": data.size,
            "content_type": mime}


@app.post("/api/jobs/{job_id}/ready")
def ready(job_id: str, request: Request, data: Ready):
    auth_check(request)
    meta = load_json(meta_path(job_id))
    for kind, key in data.files.items():
        if kind not in {"audio", "pdf", "txt", "questions"}:
            raise HTTPException(400, "유효하지 않은 종류")
        if not key.startswith(f"jobs/{job_id}/source/{kind}"):
            raise HTTPException(400, "잘못된 파일 경로")
        if not object_blob(key).exists():
            raise HTTPException(400, f"{kind} 파일이 아직 업로드되지 않았습니다.")
    if not ("audio" in data.files or "txt" in data.files):
        raise HTTPException(400, "오디오 또는 TXT 전사문을 올려주세요.")
    meta["files"] = data.files
    meta["stage"], meta["updated"] = "ready", now()
    save_json(meta_path(job_id), meta)
    return meta


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    auth_check(request)
    meta = load_json(meta_path(job_id))
    res_blob = object_blob(result_path(job_id))
    return {"meta": meta, "result": (
        json.loads(res_blob.download_as_text(encoding="utf-8"))
        if res_blob.exists() else None
    )}


@app.get("/api/jobs/{job_id}/run")
async def run_job(job_id: str, request: Request):
    auth_check(request)
    meta = load_json(meta_path(job_id))
    if meta["stage"] not in {"ready", "failed", "processing"}:
        raise HTTPException(409, "실행할 수 있는 작업이 아닙니다.")
    with active_lock:
        if job_id in active_jobs:
            raise HTTPException(409, "이미 처리 중입니다.")
        active_jobs.add(job_id)
    stream_queue: queue.Queue = queue.Queue()

    def notify(message: str):
        stream_queue.put(("progress", {"message": message, "at": now()}))

    def worker():
        try:
            pipeline(job_id, notify)
            stream_queue.put(("done", {"id": job_id}))
        except Exception as exc:
            try:
                m = load_json(meta_path(job_id))
                m["stage"], m["updated"], m["error"] = "failed", now(), str(exc)[:1000]
                save_json(meta_path(job_id), m)
            except Exception:
                pass
            stream_queue.put(("failure", {"message": str(exc)[:1000]}))
        finally:
            with active_lock:
                active_jobs.discard(job_id)

    threading.Thread(target=worker, daemon=True).start()

    async def events():
        while True:
            try:
                kind, data = await asyncio.to_thread(stream_queue.get, True, 12)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield "event: " + kind + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"
            if kind in {"done", "failure"}:
                break

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/jobs/{job_id}/block")
def edit_block(job_id: str, request: Request, change: BlockChange):
    auth_check(request)
    result = load_json(result_path(job_id))
    for b in result["blocks"]:
        if b["id"] == change.id:
            if change.corrected is not None:
                if not change.corrected.strip():
                    raise HTTPException(400, "빈 교정문은 저장할 수 없습니다.")
                b["corrected"] = change.corrected
            if change.page is not None:
                if not 1 <= change.page <= len(result["pages"]):
                    raise HTTPException(400, "PDF 범위 밖의 페이지")
                b["page"] = change.page
                b["confidence"] = 1.0
                b["flags"] = [s for s in b["flags"] if "페이지 수동 확인" not in s]
            save_json(result_path(job_id), result)
            return {"ok": True, "block": b}
    raise HTTPException(404, "문단을 찾을 수 없습니다.")


@app.get("/api/jobs/{job_id}/pdf")
def pdf_file(job_id: str, request: Request, kind: str = "pdf"):
    auth_check(request)
    meta = load_json(meta_path(job_id))
    if kind not in {"pdf", "questions"} or kind not in meta["files"]:
        raise HTTPException(404, "PDF 없음")
    raw = object_blob(meta["files"][kind]).download_as_bytes()
    return Response(raw, media_type="application/pdf",
                    headers={"Cache-Control": "private, max-age=300"})


@app.get("/api/jobs/{job_id}/download")
def download(job_id: str, request: Request, mode: str = "corrected"):
    auth_check(request)
    obj = load_json(result_path(job_id))
    if mode == "raw":
        lines = [b["raw"] for b in obj["blocks"]]
    elif mode == "markdown":
        lines = []
        for b in obj["blocks"]:
            lines.append(f"### {b['id']} · PDF {b['page'] or '미매칭'}p")
            lines.append(b["corrected"])
            lines.append("")
    else:
        lines = [b["corrected"] for b in obj["blocks"]]
    content = "\n\n".join(lines)
    return Response(content, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="lecture_{mode}.txt"'})


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    auth_check(request)
    load_json(meta_path(job_id))
    count = 0
    for blob in storage_client().list_blobs(BUCKET, prefix=f"jobs/{job_id}/"):
        blob.delete()
        count += 1
    return {"ok": True, "deleted_objects": count}
