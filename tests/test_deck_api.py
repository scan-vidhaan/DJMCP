from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import djmcp.routes.library as lib
from djmcp.server import app


@pytest.fixture
def client(synthetic_dirs, synthetic_track, monkeypatch):
    tracks_dir, processed_dir = synthetic_dirs
    monkeypatch.setattr(lib, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(lib, "TRACKS_DIR", tracks_dir)
    return TestClient(app)


def test_peaks_shape_and_cache(client, synthetic_track, synthetic_dirs):
    tracks_dir, _ = synthetic_dirs
    first = client.get(f"/api/library/{synthetic_track}/peaks?bins=100").json()["peaks"]
    assert len(first) == 100 and max(first) == 1.0 and min(first) >= 0
    assert (tracks_dir / f"{synthetic_track}.peaks100.json").exists()
    assert client.get(f"/api/library/{synthetic_track}/peaks?bins=100").json()["peaks"] == first


def test_peaks_unknown_and_unsafe_ids(client):
    assert client.get("/api/library/nope/peaks").status_code == 404
    assert client.get("/api/library/..%2Fx/peaks").status_code in (400, 404)


def test_fx_commit_renders_chain(client, synthetic_track):
    chain = [
        {"tool": "eq", "params": {"low_gain": 6, "mid_gain": 0, "high_gain": 0}},
        {"tool": "filter", "params": {"type": "lowpass", "cutoff_hz": 4000}},
    ]
    res = client.post("/api/fx/commit", json={"track_id": synthetic_track, "chain": chain})
    assert res.status_code == 200
    body = res.json()
    assert body["track_id"] != synthetic_track and body["duration"] > 10


def test_fx_commit_rejects_bad_requests(client, synthetic_track):
    assert client.post("/api/fx/commit", json={"track_id": synthetic_track, "chain": []}).status_code == 400
    bad = {"track_id": synthetic_track, "chain": [{"tool": "flanger", "params": {}}]}
    assert client.post("/api/fx/commit", json=bad).status_code == 400
    missing = {"track_id": "nope", "chain": [{"tool": "eq", "params": {}}]}
    assert client.post("/api/fx/commit", json=missing).status_code == 404
