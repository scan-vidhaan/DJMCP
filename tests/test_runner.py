from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from djmcp import config, runner
from djmcp.server import app
from djmcp.tools import state

FAKE = Path(__file__).parent / "fake_claude.py"


@pytest.fixture
def client(monkeypatch, tmp_path):
    db = tmp_path / "state.db"
    monkeypatch.setattr(config, "STATE_DB_PATH", db)
    monkeypatch.setenv("DJMCP_STATE_DB", str(db))  # the fake claude subprocess reads this
    monkeypatch.setenv("DJMCP_CLAUDE_CMD", f'"{sys.executable}" "{FAKE}"')
    monkeypatch.setenv("PYTHONPATH", str(config.REPO_ROOT))
    runner._procs.clear()
    runner._logs.clear()
    return TestClient(app)


def wait_for(client, job_id, predicate, timeout=30):
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/state/jobs/{job_id}").json()
        if predicate(job):
            return job
        time.sleep(0.2)
    raise AssertionError(f"timed out; last job state: {job}")


def test_question_then_answer_then_done(client):
    job_id = client.post("/api/requests", json={"text": "make a mashup"}).json()["job_id"]

    job = wait_for(client, job_id, lambda j: j["status"] == "waiting_input")
    assert job["question"]["key"] == "style" and job["question"]["options"] == ["Sequence", "Layered"]

    assert client.post(f"/api/requests/{job_id}/answer", json={"key": "style", "answer": "Layered"}).status_code == 200
    job = wait_for(client, job_id, lambda j: j["status"] == "done")
    assert job["result"] == {"track_id": "fake-output"}
    texts = [e.get("text") for e in client.get(f"/api/requests/{job_id}/log").json()["events"]]
    assert "Using style Layered." in texts


def test_autopilot_never_asks(client):
    job_id = client.post("/api/requests", json={"text": "make a mashup", "autopilot": True}).json()["job_id"]
    job = wait_for(client, job_id, lambda j: j["status"] == "done")
    assert any("Sequence" in a for a in job["assumptions"])


def test_crash_marks_job_failed_with_reason(client):
    job_id = client.post("/api/requests", json={"text": "crash please"}).json()["job_id"]
    job = wait_for(client, job_id, lambda j: j["status"] == "failed")
    assert "exit 3" in job["error"] and "boom" in job["error"]


def test_stopping_early_is_resumable(client):
    job_id = client.post("/api/requests", json={"text": "quit-early"}).json()["job_id"]
    job = wait_for(client, job_id, lambda j: j["status"] == "failed")
    assert "Resume" in job["error"]
    assert job_id in [j["job_id"] for j in client.get("/api/state/jobs").json()]


def test_empty_request_rejected(client):
    assert client.post("/api/requests", json={"text": "  "}).status_code == 400


def test_missing_claude_gives_clear_error(client, monkeypatch):
    monkeypatch.delenv("DJMCP_CLAUDE_CMD")
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)
    monkeypatch.setattr(runner, "_find_vscode_binary", lambda: None)  # this machine may have the extension
    res = client.post("/api/requests", json={"text": "hi"})
    assert res.status_code == 503 and "Claude Code" in res.json()["detail"]
    assert client.get("/api/system/check").json()["available"] is False
    assert client.get("/api/state/jobs").json() == []  # no orphan job left behind


def test_ui_focus_and_ping(client):
    assert client.get("/api/ui/status").json()["open"] is False
    client.post("/api/ui/ping")
    client.post("/api/ui/focus", json={"job_id": "abc"})
    status = client.get("/api/ui/status").json()
    assert status["open"] is True and status["focus_job"] == "abc"


def test_library_audio_rejects_traversal_and_lists(client, synthetic_dirs, synthetic_track, monkeypatch):
    import djmcp.routes.library as lib

    tracks_dir, processed_dir = synthetic_dirs
    monkeypatch.setattr(lib, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(lib, "TRACKS_DIR", tracks_dir)
    (processed_dir / "out-1.mp3").write_bytes((tracks_dir / f"{synthetic_track}.mp3").read_bytes())

    assert client.get("/api/audio/..%2Fsecret").status_code in (400, 404)
    assert client.get("/api/audio/out-1").status_code == 200
    assert [t["track_id"] for t in client.get("/api/library/processed").json()] == ["out-1"]

    client.put("/api/library/out-1/cues", json={"cues": [{"time": 12.5, "label": "drop"}]})
    assert client.get("/api/library/out-1/cues").json()["cues"][0]["label"] == "drop"


def test_continuing_an_old_job_hands_work_back_to_it(client):
    old_id = state.state_create_job("dj-orchestrator", "earlier mashup", {})
    state.state_update(old_id, "download_1", "done")
    new_id = client.post("/api/requests", json={"text": f"continue-old:{old_id}"}).json()["job_id"]

    wait_for(client, new_id, lambda j: j["status"] == "done")
    # the earlier job's own run started: the fake asks its question, parking it
    old = wait_for(client, old_id, lambda j: j["status"] == "waiting_input")
    assert old["question"]["key"] == "style"


def test_finds_newest_vscode_extension_binary(monkeypatch, tmp_path):
    name = "claude.exe" if sys.platform == "win32" else "claude"
    for version in ("2.1.284", "2.1.301", "2.1.9"):
        binary = tmp_path / ".vscode" / "extensions" / f"anthropic.claude-code-{version}-win32-x64" / "resources" / "native-binary" / name
        binary.parent.mkdir(parents=True)
        binary.write_text("")
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path)
    assert "2.1.301" in runner._find_vscode_binary()  # numeric compare: 2.1.301 > 2.1.9


def test_no_vscode_extension_means_none(monkeypatch, tmp_path):
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path)
    assert runner._find_vscode_binary() is None
