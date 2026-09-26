import pytest

from djmcp.tools import web_search, youtube


def test_extract_candidates_filters_non_youtube_and_dedupes():
    hits = [
        {"url": "https://www.daft.ie/property-for-sale", "title": "Daft.ie"},
        {
            "url": "https://www.youtube.com/watch?v=FGBhQbmPwH8&list=xyz",
            "title": "Daft Punk - One More Time (Official Video) - YouTube",
        },
        {"url": "https://m.youtube.com/watch?v=A2VpR8HahKc", "title": "One More Time (Audio) - YouTube"},
        {"url": "https://www.youtube.com/watch?v=FGBhQbmPwH8", "title": "duplicate"},
    ]
    candidates = web_search._extract_candidates(hits, limit=5)
    assert candidates == [
        ("FGBhQbmPwH8", "Daft Punk - One More Time (Official Video)"),
        ("A2VpR8HahKc", "One More Time (Audio)"),
    ]


def test_extract_candidates_respects_limit():
    hits = [{"url": f"https://www.youtube.com/watch?v=vid{i:08d}", "title": "x"} for i in range(5)]
    assert len(web_search._extract_candidates(hits, limit=2)) == 2


@pytest.mark.integration
async def test_search_finds_real_song():
    results = await youtube.search_song("Daft Punk One More Time", limit=3)
    assert results
    assert results[0]["url"].startswith("http")
    assert results[0]["source"] == "web"


@pytest.mark.integration
async def test_search_ddg_fallback_when_firecrawl_empty(monkeypatch):
    # Force Firecrawl to look empty (as it would on a bad day / rate limit)
    # so we're testing that the DuckDuckGo fallback finds something real.
    monkeypatch.setattr(web_search, "_firecrawl_search", lambda query, limit: [])
    results = await youtube.search_song("Daft Punk One More Time", limit=3)
    assert results
    assert all(r["source"] == "web" for r in results)
