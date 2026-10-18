"""Trend discovery for vague requests ("trending Bollywood songs").

Returns raw chart-page hits plus an excerpt of the top pages. The agent
(an LLM) reads the titles and excerpts and decides which songs are actually
on the chart -- parsing arbitrary chart pages with regexes would break every
time a site changes its layout. Song names it picks go through search_song.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os

import requests
from ddgs import DDGS

logger = logging.getLogger(__name__)

FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"
TIMEOUT_SEC = 25
EXCERPT_CHARS = 3000
EXCERPT_PAGES = 2


def _headers() -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _search(query: str, limit: int) -> list[dict]:
    """Blocking. Firecrawl first, DuckDuckGo if it fails or finds nothing."""
    try:
        response = requests.post(
            FIRECRAWL_SEARCH_URL,
            json={"query": query, "limit": limit, "sources": ["web"]},
            headers=_headers(),
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
        hits = response.json().get("data", {}).get("web", []) or []
        results = [
            {"title": h.get("title", ""), "url": h.get("url", ""), "snippet": h.get("description", "")}
            for h in hits
        ]
        if results:
            return results
    except Exception:
        logger.exception("firecrawl search failed for query=%r", query)

    try:
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=limit))
        return [{"title": h.get("title", ""), "url": h.get("href", ""), "snippet": h.get("body", "")} for h in hits]
    except Exception:
        logger.exception("duckduckgo search failed for query=%r", query)
        return []


def _scrape(url: str) -> str:
    """Blocking, best effort: markdown excerpt of a page, or ''."""
    try:
        response = requests.post(
            FIRECRAWL_SCRAPE_URL,
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            headers=_headers(),
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
        markdown = response.json().get("data", {}).get("markdown", "") or ""
        return markdown[:EXCERPT_CHARS]
    except Exception:
        logger.warning("scrape failed for url=%r", url)
        return ""


def _find_trending_blocking(region: str, genre: str, limit: int) -> dict:
    now = datetime.date.today()
    query = f"top {genre} songs {region} this week chart {now:%B %Y}"
    results = _search(query, limit)
    for hit in results[:EXCERPT_PAGES]:
        excerpt = _scrape(hit["url"]) if hit["url"] else ""
        if excerpt:
            hit["page_excerpt"] = excerpt
    return {"query": query, "as_of": now.isoformat(), "results": results}


async def find_trending(region: str = "India", genre: str = "Bollywood", limit: int = 8) -> dict:
    """Search current charts for a region/genre. The caller extracts song names."""
    return await asyncio.to_thread(_find_trending_blocking, region, genre, limit)
