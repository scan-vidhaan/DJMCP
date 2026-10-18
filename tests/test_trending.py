from __future__ import annotations

from djmcp.tools import trending


async def test_find_trending_returns_hits_with_excerpts(monkeypatch):
    hits = [
        {"title": "Top 10 Bollywood songs", "url": "https://a.example/1", "snippet": "s"},
        {"title": "Chart B", "url": "https://b.example/2", "snippet": "s"},
        {"title": "Chart C", "url": "https://c.example/3", "snippet": "s"},
    ]
    monkeypatch.setattr(trending, "_search", lambda query, limit: [dict(h) for h in hits])
    monkeypatch.setattr(trending, "_scrape", lambda url: f"excerpt of {url}")

    result = await trending.find_trending("India", "Bollywood", 8)

    assert "Bollywood" in result["query"] and "India" in result["query"]
    assert result["results"][0]["page_excerpt"] == "excerpt of https://a.example/1"
    assert "page_excerpt" in result["results"][1]
    assert "page_excerpt" not in result["results"][2]  # only the top pages are fetched


async def test_find_trending_survives_failed_scrape(monkeypatch):
    monkeypatch.setattr(trending, "_search", lambda q, n: [{"title": "t", "url": "https://x", "snippet": ""}])
    monkeypatch.setattr(trending, "_scrape", lambda url: "")
    result = await trending.find_trending()
    assert result["results"][0]["title"] == "t" and "page_excerpt" not in result["results"][0]
