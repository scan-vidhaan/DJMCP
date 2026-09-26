"""Lyrics transcription with timestamps.

Gives the orchestrator a way to reason about *what* is happening at a given
point in a track when deciding what to remix -- e.g. "find the line where
the hook lands" or "don't cut mid-word" -- rather than only BPM/energy
(see djmcp/tools/analysis.py, phase 2).

Runs on the full downloaded mix, not an isolated vocal stem: stem
separation (demucs) is a heavier, separate dependency reserved for the
boosters/mashup phases. Quality is usable for most vocal-forward tracks;
instrumental-heavy sections will transcribe as empty or garbled text.

Transcripts are cached as a JSON sidecar next to the track (same pattern
analyze_track uses), since re-running Whisper on every call would be slow.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from faster_whisper import WhisperModel

from djmcp.config import TRACKS_DIR
from djmcp.tools.common import resolve_track_path

logger = logging.getLogger(__name__)

DEFAULT_MODEL_SIZE = "base"

_model_cache: dict[str, WhisperModel] = {}


def _get_model(model_size: str) -> WhisperModel:
    model = _model_cache.get(model_size)
    if model is None:
        # int8 on CPU: no GPU assumed for a localhost app, and this keeps
        # memory/latency reasonable for base/small models.
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        _model_cache[model_size] = model
    return model


def _cache_path(track_id: str) -> Path:
    return TRACKS_DIR / f"{track_id}.transcript.json"


def _transcribe_blocking(track_id: str, model_size: str, language: str | None) -> dict:
    audio_path = resolve_track_path(track_id)
    if audio_path is None:
        raise FileNotFoundError(f"no downloaded track for track_id={track_id!r}")

    model = _get_model(model_size)
    segment_iter, info = model.transcribe(
        str(audio_path), word_timestamps=True, language=language
    )

    segments = []
    for seg in segment_iter:
        segments.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "words": [
                    {"start": round(w.start, 2), "end": round(w.end, 2), "word": w.word}
                    for w in (seg.words or [])
                ],
            }
        )

    return {
        "track_id": track_id,
        "language": info.language,
        "language_requested": language,
        "duration": round(info.duration, 2),
        "model": model_size,
        "segments": segments,
    }


async def transcribe_track(
    track_id: str,
    model_size: str = DEFAULT_MODEL_SIZE,
    language: str | None = None,
    force: bool = False,
) -> dict:
    """Transcribe a downloaded track to timestamped lyrics. Cached to a JSON sidecar.

    language is an ISO 639-1 code (e.g. "en", "kn", "hi"). Whisper's own
    auto-detection can pick the wrong language for a track (confirmed on a
    Kannada song misdetected as Malayalam), which then hurts transcription
    accuracy too -- so the caller (the orchestrating agent, which usually
    has more context on the track than the audio alone gives) can pass an
    explicit hint instead of relying on auto-detect. None keeps auto-detect.
    """
    cache_path = _cache_path(track_id)
    if not force and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    result = await asyncio.to_thread(_transcribe_blocking, track_id, model_size, language)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
