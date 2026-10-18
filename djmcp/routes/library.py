"""Finished-output library for the deck: list, stream audio, cue points."""

from __future__ import annotations

import json
import re

import librosa
import numpy as np

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from djmcp.config import EXPORTS_DIR, PROCESSED_DIR, TRACKS_DIR
from djmcp.tools import state

router = APIRouter(prefix="/api", tags=["library"])

_SAFE_ID = re.compile(r"^[\w.\-]+$")


def _safe_id(track_id: str) -> str:
    if not _SAFE_ID.match(track_id) or ".." in track_id:
        raise HTTPException(status_code=400, detail="invalid track id")
    return track_id


def _sidecar_info(track_id: str) -> dict:
    sidecar = TRACKS_DIR / f"{track_id}.json"
    if not sidecar.exists():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {"bpm": data.get("bpm"), "key": data.get("key"), "camelot": data.get("camelot")}


def _jobs_by_result() -> dict[str, dict]:
    """track_id -> {job_id, goal} for finished jobs, to show where an output came from."""
    mapping = {}
    for job in state.state_list_closed(limit=200):
        track_id = (job.get("result") or {}).get("track_id")
        if track_id:
            mapping[track_id] = {"job_id": job["job_id"], "goal": job["goal"]}
    return mapping


@router.get("/library/processed")
def list_processed() -> list[dict]:
    origins = _jobs_by_result()
    items = []
    for path in sorted(PROCESSED_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True):
        track_id = path.stem
        items.append(
            {
                "track_id": track_id,
                "size_bytes": path.stat().st_size,
                "modified": path.stat().st_mtime,
                "job": origins.get(track_id),
                **_sidecar_info(track_id),
            }
        )
    return items


@router.get("/audio/{track_id}")
def audio(track_id: str) -> FileResponse:
    track_id = _safe_id(track_id)
    for directory in (PROCESSED_DIR, EXPORTS_DIR, TRACKS_DIR):
        candidate = directory / f"{track_id}.mp3"
        if candidate.exists():
            return FileResponse(candidate, media_type="audio/mpeg", filename=f"{track_id}.mp3")
    raise HTTPException(status_code=404, detail="track not found")


def _find_audio(track_id: str):
    for directory in (PROCESSED_DIR, EXPORTS_DIR, TRACKS_DIR):
        candidate = directory / f"{track_id}.mp3"
        if candidate.exists():
            return candidate
    return None


@router.get("/library/{track_id}/peaks")
def peaks(track_id: str, bins: int = 900) -> dict:
    """Waveform outline for the deck: `bins` loudness values in 0..1. Cached next to the track."""
    track_id = _safe_id(track_id)
    bins = max(50, min(bins, 4000))
    path = _find_audio(track_id)
    if path is None:
        raise HTTPException(status_code=404, detail="track not found")

    cache = path.with_name(f"{track_id}.peaks{bins}.json")
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))

    y, _ = librosa.load(str(path), sr=8000, mono=True)
    usable = (len(y) // bins) * bins
    if usable == 0:
        result = {"peaks": [0.0] * bins}
    else:
        outline = np.abs(y[:usable]).reshape(bins, -1).max(axis=1)
        top = float(outline.max()) or 1.0
        result = {"peaks": [round(float(v) / top, 3) for v in outline]}
    cache.write_text(json.dumps(result), encoding="utf-8")
    return result


class Cues(BaseModel):
    cues: list[dict]


def _cue_path(track_id: str):
    return PROCESSED_DIR / f"{_safe_id(track_id)}.cues.json"


@router.get("/library/{track_id}/cues")
def get_cues(track_id: str) -> dict:
    path = _cue_path(track_id)
    if not path.exists():
        return {"cues": []}
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("/library/{track_id}/cues")
def put_cues(track_id: str, body: Cues) -> dict:
    _cue_path(track_id).write_text(json.dumps(body.model_dump()), encoding="utf-8")
    return body.model_dump()
