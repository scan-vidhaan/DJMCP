from __future__ import annotations

import pytest

from djmcp import config
from djmcp.tools import state


@pytest.fixture(autouse=True)
def state_db(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STATE_DB_PATH", tmp_path / "state.db")


def test_next_step_follows_sequence():
    job_id = state.state_create_job("mashup-builder", "a x b")
    state.state_update(job_id, "search", "done", {"a": "url1"})
    state.state_update(job_id, "download_a", "done", {"track_id": "t1"})
    got = state.state_get(job_id)
    assert got["next_step"] == "download_b"
    assert got["steps"][1]["artifacts"] == {"track_id": "t1"}


def test_persists_across_engine_restart():
    job_id = state.state_create_job("mashup-builder", "goal")
    state.state_update(job_id, "search", "done")
    state._engine = None  # simulate process restart
    assert [j["job_id"] for j in state.state_list_open()] == [job_id]


def test_failed_step_still_listed_for_resume():
    job_id = state.state_create_job("mashup-builder", "goal")
    state.state_update(job_id, "search", "failed", error="no results")
    jobs = state.state_list_open()
    assert jobs[0]["status"] == "failed" and jobs[0]["error"] == "no results"
    assert state.state_list_open(include_failed=False) == []
    assert state.state_resume(job_id)["status"] == "open"


def test_completing_all_steps_closes_job():
    job_id = state.state_create_job("mashup-builder", "goal")
    for step in state.AGENT_STEPS["mashup-builder"]:
        state.state_update(job_id, step, "done")
    assert state.state_get(job_id)["status"] == "done"
    assert state.state_list_open() == []
    assert len(state.state_list_closed()) == 1


def test_dynamic_agent_next_step_is_first_pending():
    job_id = state.state_create_job("set-builder", "goal")
    state.state_update(job_id, "track_1", "done")
    state.state_update(job_id, "track_2", "pending")
    assert state.state_get(job_id)["next_step"] == "track_2"


def test_unknown_job():
    with pytest.raises(KeyError):
        state.state_get("nope")
