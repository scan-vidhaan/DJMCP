"""Paths and defaults for the DJ MCP server."""

import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STORAGE_DIR = REPO_ROOT / "djmcp" / "storage"
TRACKS_DIR = STORAGE_DIR / "tracks"
PROCESSED_DIR = STORAGE_DIR / "processed"
LOOPS_DIR = STORAGE_DIR / "loops"
EXPORTS_DIR = STORAGE_DIR / "exports"
STATE_DB_PATH = STORAGE_DIR / "state.db"

for _dir in (TRACKS_DIR, PROCESSED_DIR, LOOPS_DIR, EXPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# Portable ffmpeg: repo ships its own build under bin/ffmpeg/ so users don't
# need a system-wide install. Falls back to PATH if the bundled copy isn't
# there (e.g. a system ffmpeg is already installed).
_BUNDLED_FFMPEG_DIR = REPO_ROOT / "bin" / "ffmpeg" / "bin"


def _find_bundled(binary: str) -> str | None:
    candidate = _BUNDLED_FFMPEG_DIR / f"{binary}.exe"
    if candidate.exists():
        return str(candidate)
    candidate = _BUNDLED_FFMPEG_DIR / binary
    if candidate.exists():
        return str(candidate)
    return None


FFMPEG_PATH = _find_bundled("ffmpeg") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_PATH = _find_bundled("ffprobe") or shutil.which("ffprobe") or "ffprobe"

HOST = os.environ.get("DJMCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("DJMCP_PORT", "8000"))
