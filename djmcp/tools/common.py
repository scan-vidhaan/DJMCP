"""Shared helpers for tools/*.py."""

from __future__ import annotations

from pathlib import Path

from djmcp.config import PROCESSED_DIR, TRACKS_DIR


def resolve_track_path(track_id: str) -> Path | None:
    """Find a track's audio file by id, checking originals then processed outputs."""
    for directory in (TRACKS_DIR, PROCESSED_DIR):
        candidate = directory / f"{track_id}.mp3"
        if candidate.exists():
            return candidate
    return None
