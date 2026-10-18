"""Export: copy finished tracks to storage/exports/, or cut a social-ready clip."""

from __future__ import annotations

from pydub import AudioSegment

from djmcp.config import EXPORTS_DIR
from djmcp.tools import analysis
from djmcp.tools.common import resolve_track_path
from djmcp.tools.dsp import new_track_id

FADE_MS = 500
CLIP_MAX_SEC = {"ig": 90, "tiktok": 60, "shorts": 60}


def _load(track_id: str) -> AudioSegment:
    path = resolve_track_path(track_id)
    if path is None:
        raise FileNotFoundError(f"no track found for track_id={track_id!r}")
    return AudioSegment.from_file(path)


def export_mp3(track_id: str, bitrate: int = 320) -> dict:
    """Encode a track to storage/exports/{track_id}.mp3 at the given bitrate."""
    audio = _load(track_id)
    out_path = EXPORTS_DIR / f"{track_id}.mp3"
    audio.export(out_path, format="mp3", bitrate=f"{bitrate}k")
    return {"track_id": track_id, "path": str(out_path), "duration": audio.duration_seconds}


def short_clip(track_id: str, duration: float = 30, format: str = "ig") -> dict:
    """A fade-in/out clip centered on the track's highest-energy section."""
    if format not in CLIP_MAX_SEC:
        raise ValueError(f"format must be one of {tuple(CLIP_MAX_SEC)}, got {format!r}")
    duration = min(duration, CLIP_MAX_SEC[format])

    audio = _load(track_id)
    sections = analysis.analyze_track(track_id)["sections"]
    peak = max(sections, key=lambda s: s["energy"]) if sections else None
    center = (peak["start"] + peak["end"]) / 2 if peak else audio.duration_seconds / 2

    start = max(0.0, min(center - duration / 2, audio.duration_seconds - duration))
    clip = audio[start * 1000 : (start + duration) * 1000].fade_in(FADE_MS).fade_out(FADE_MS)

    clip_id = new_track_id(track_id, f"clip-{format}", round(start, 2), duration)
    out_path = EXPORTS_DIR / f"{clip_id}.mp3"
    clip.export(out_path, format="mp3", bitrate="320k")
    return {"track_id": clip_id, "path": str(out_path), "duration": clip.duration_seconds}
