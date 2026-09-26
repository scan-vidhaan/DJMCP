"""Web-search discovery path: Firecrawl first, DuckDuckGo as a fallback.

Used by djmcp.tools.youtube.search_song as the primary way to find a song's
YouTube URL. Deliberately does not call yt-dlp's own search here: YouTube's
extractor can be slow or rate-limited independent of network speed, while a
plain web search restricted to `site:youtube.com` is fast and reliable.
Because of that, `duration` is always 0 (unknown) here -- the real value
gets filled in once the track is downloaded and analyzed (see
djmcp/tools/analysis.py, phase 2).

Firecrawl's /v2/search works without an API key (a rate-limited "keyless"
tier). Set FIRECRAWL_API_KEY to raise those limits -- see
https://docs.firecrawl.dev/rate-limits. DuckDuckGo only runs when Firecrawl
comes back empty.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

import requests
from ddgs import DDGS

logger = logging.getLogger(__name__)

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_TIMEOUT_SEC = 20
_VIDEO_ID_RE = re.compile(r"[?&]v=([a-zA-Z0-9_-]{11})")
_YOUTUBE_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*YouTube\s*$")


def _firecrawl_search(query: str, limit: int) -> list[dict]:
    """Blocking; run via asyncio.to_thread."""
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {"query": f"site:youtube.com {query}", "limit": limit, "sources": ["web"]}
    response = requests.post(
        FIRECRAWL_SEARCH_URL, json=payload, headers=headers, timeout=FIRECRAWL_TIMEOUT_SEC
    )
    response.raise_for_status()
    data = response.json()
    hits = data.get("data", {}).get("web", []) or []
    return [{"url": h.get("url", ""), "title": h.get("title", "")} for h in hits]


def _ddg_search(query: str, limit: int) -> list[dict]:
    """Blocking; run via asyncio.to_thread. Fallback when Firecrawl finds nothing."""
    with DDGS() as ddgs:
        hits = list(ddgs.text(f"site:youtube.com {query}", max_results=limit))
    return [{"url": h.get("href", ""), "title": h.get("title", "")} for h in hits]


def _extract_candidates(hits: list[dict], limit: int) -> list[tuple[str, str]]:
    """Pull unique (video_id, title) pairs out of search hits shaped {url, title}."""
    candidates: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    for hit in hits:
        if len(candidates) >= limit:
            break
        match = _VIDEO_ID_RE.search(hit.get("url", ""))
        if not match:
            continue
        video_id = match.group(1)
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        title = _YOUTUBE_TITLE_SUFFIX_RE.sub("", hit.get("title", "")).strip()
        candidates.append((video_id, title))
    return candidates


def _to_results(candidates: list[tuple[str, str]]) -> list[dict]:
    return [
        {
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "duration": 0,
            "uploader": "",
            "thumbnail": "",
            "source": "web",
        }
        for video_id, title in candidates
    ]


async def find_youtube(query: str, limit: int = 5) -> list[dict]:
    """Firecrawl search restricted to youtube.com; DuckDuckGo if that's empty."""
    try:
        hits = await asyncio.to_thread(_firecrawl_search, query, limit * 3)
    except Exception:
        logger.exception("firecrawl search failed for query=%r", query)
        hits = []

    candidates = _extract_candidates(hits, limit)
    if candidates:
        return _to_results(candidates)

    logger.info("firecrawl found nothing for query=%r, falling back to duckduckgo", query)
    try:
        ddg_hits = await asyncio.to_thread(_ddg_search, query, limit * 3)
    except Exception:
        logger.exception("duckduckgo search failed for query=%r", query)
        ddg_hits = []

    return _to_results(_extract_candidates(ddg_hits, limit))
