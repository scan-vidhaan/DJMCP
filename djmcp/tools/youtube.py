"""YouTube discovery + download.

Discovery (search_song) delegates entirely to djmcp.tools.web_search
(Firecrawl, with DuckDuckGo as its own fallback) rather than yt-dlp's
ytsearch: YouTube's own search extractor can stall for minutes on a single
request (rate-limiting, a slow signature challenge) independent of network
speed, which made it an unreliable primary path. Download still uses
yt-dlp directly -- that part works fine once given a concrete URL.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from pathlib import Path
from typing import Callable

import yt_dlp

from djmcp.config import FFMPEG_PATH, TRACKS_DIR
from djmcp.tools import web_search

logger = logging.getLogger(__name__)

# Bounds probe_duration so a stuck yt-dlp lookup falls through to "unknown
# duration" (0) in a few seconds rather than hanging the /download request.
PROBE_TIMEOUT_SEC = 10

# yt-dlp has no timeout by default and can retry network hiccups for minutes.
# Every YoutubeDL() call in this module starts from this base so a flaky
# connection fails fast instead of hanging a request indefinitely.
_YDL_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
    "retries": 2,
    "extractor_retries": 1,
}


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "track"


async def search_song(query: str, limit: int = 5) -> list[dict]:
    """Search for a song's YouTube URL via djmcp.tools.web_search."""
    return await web_search.find_youtube(query, limit)


def _probe_duration(url: str) -> int:
    ydl_opts = {**_YDL_BASE_OPTS, "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("duration") or 0


async def probe_duration(url: str) -> int:
    """Cheap metadata-only lookup, used by the download route to decide sync vs. background.

    A stuck probe falls through to "unknown duration" (0) rather than hang
    the /download request.
    """
    try:
        return await asyncio.wait_for(asyncio.to_thread(_probe_duration, url), timeout=PROBE_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("probe_duration timed out after %ss for url=%r", PROBE_TIMEOUT_SEC, url)
        return 0


def download_song(
    url: str,
    out_dir: Path | None = None,
    progress_hook: Callable[[dict], None] | None = None,
) -> dict:
    """Download bestaudio, convert to 320kbps mp3, save under storage/tracks/. Blocking."""
    out_dir = out_dir or TRACKS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        **_YDL_BASE_OPTS,
        "format": "bestaudio/best",
        "ffmpeg_location": FFMPEG_PATH,
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
    }
    if progress_hook is not None:
        ydl_opts["progress_hooks"] = [progress_hook]

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "track")
    video_id = info.get("id", "")
    duration = info.get("duration") or 0

    slug = _slugify(title)
    short_hash = hashlib.sha1(video_id.encode()).hexdigest()[:8]
    track_id = f"{slug}-{short_hash}"

    downloaded_path = out_dir / f"{video_id}.mp3"
    final_path = out_dir / f"{track_id}.mp3"
    if downloaded_path.exists() and downloaded_path != final_path:
        downloaded_path.replace(final_path)
    elif downloaded_path.exists():
        final_path = downloaded_path

    return {
        "track_id": track_id,
        "path": str(final_path),
        "title": title,
        "duration": duration,
    }
