"""Import locally transcribed WhisperKit JSON/SRT/VTT/TXT without cloud STT.

Designed for the open-source iOS Whisperkit app export:
https://github.com/yu314-coder/WhisperKit/blob/main/whisper/TranscriptExporter.swift
No external packages required.
"""
from __future__ import annotations
import json
import re
from pathlib import Path


def _time_seconds(value: str) -> float:
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"자막 시간 형식이 올바르지 않습니다: {value[:24]}")
    try:
        if len(parts) == 2:
            mm, ss = parts
            return 60 * int(mm) + float(ss)
        hh, mm, ss = parts
        return 3600 * int(hh) + 60 * int(mm) + float(ss)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"자막 시간 형식이 올바르지 않습니다: {value[:24]}") from exc


def _normalize_segment(start, end, words, speaker=None):
    text = str(words or "").strip()
    if not text:
        return None
    if speaker and not text.startswith(f"{speaker}:"):
        text = f"{speaker}: {text}"
    try:
        start = max(0.0, float(start))
        end = max(start, float(end))
    except (ValueError, TypeError) as exc:
        raise ValueError("전사문 구간의 시작·종료 시간이 숫자가 아닙니다.") from exc
    if start > 10000000 or end > 10000000:
        raise ValueError("전사문 시간 값이 너무 큽니다.")
    return {"text": text, "start": round(start, 3),
            "end": round(end, 3), "chunk": None}


def parse_local_transcript(path: str | Path) -> dict:
    """Return dict with segments, audio duration (optional), language/model.

    For JSON translated transcripts, prefer 'original' (spoken words) over
    translated 'text'. Do not alter or delete any recognized content.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix not in {".json", ".srt", ".vtt", ".txt"}:
        raise ValueError("Whisper 전사문은 JSON, SRT, VTT, TXT 형식으로 내보내 주세요.")
    source = p.read_text(encoding="utf-8-sig", errors="strict").replace("\r\n", "\n")
    segments, model, language, duration = [], None, None, None
    if suffix == ".json":
        try:
            obj = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError("Whisper JSON 문법 오류입니다.") from exc
        if not isinstance(obj, dict):
            raise ValueError("Whisper JSON 최상위 객체는 딕셔너리여야 합니다.")
        model = obj.get("model")
        language = obj.get("spokenLanguage") or obj.get("language")
        duration = obj.get("duration")
        payload = obj.get("segments")
        if not isinstance(payload, list):
            raise ValueError("Whisper JSON에 segments 배열이 없습니다.")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Whisper JSON segments 항목은 객체여야 합니다.")
            original = item.get("original")
            words = original if isinstance(original, str) and original.strip() else item.get("text")
            seg = _normalize_segment(
                item.get("start", item.get("startTime")),
                item.get("end", item.get("endTime")),
                words, item.get("speaker")
            )
            if seg:
                segments.append(seg)
        if not segments:
            raw = obj.get("spokenText") or obj.get("text")
            if isinstance(raw, str) and raw.strip():
                segments = [{"text": raw.strip(), "start": None, "end": None, "chunk": None}]
    elif suffix in {".srt", ".vtt"}:
        body = re.sub(r"^\ufeff?WEBVTT[^\n]*\n", "", source)
        for cue in re.split(r"\n\s*\n", body):
            lines = [l.strip() for l in cue.strip().splitlines() if l.strip()]
            if not lines:
                continue
            stamp_idx = next((i for i, l in enumerate(lines) if " --> " in l), None)
            if stamp_idx is None:
                continue
            startstr, endstr = lines[stamp_idx].split(" --> ", 1)
            endstr = endstr.split()[0]
            start, end = _time_seconds(startstr), _time_seconds(endstr)
            text = "\n".join(lines[stamp_idx+1:]).strip()
            text = re.sub(r"^<v\s+([^>]+)>", r"\1: ", text)
            seg = _normalize_segment(start, end, text)
            if seg:
                segments.append(seg)
    else:
        # WhisperKit TXT contains one utterance per line. Keep order and words;
        # no timestamps exist in this format.
        segments = [
            {"text": line.strip(), "start": None, "end": None, "chunk": None}
            for line in source.splitlines() if line.strip()
        ]
    if not segments:
        raise ValueError("Whisper 파일에서 전사 내용을 찾지 못했습니다.")
    try:
        duration = max(0.0, float(duration)) if duration is not None else None
    except (ValueError, TypeError):
        duration = None
    if duration is None:
        duration = max((s["end"] for s in segments if s["end"] is not None), default=None)
    return {
        "segments": segments,
        "duration": duration,
        "model": model if isinstance(model, str) else None,
        "language": language if isinstance(language, str) else None,
    }
