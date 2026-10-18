from __future__ import annotations

import pytest

from djmcp import config
from djmcp.tools import state


@pytest.fixture(autouse=True)
def state_db(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STATE_DB_PATH", tmp_path / "state.db")


@pytest.fixture
def fixed_sequence(monkeypatch):
    monkeypatch.setitem(state.AGENT_STEPS, "seq-agent", ["a", "b", "c"])


def test_next_step_follows_fixed_sequence(fixed_sequence):
    job_id = state.state_create_job("seq-agent", "goal")
    state.state_update(job_id, "a", "done", {"x": 1})
    got = state.state_update(job_id, "b", "done", {"track_id": "t1"})
    assert got["next_step"] == "c"
    assert got["steps"][1]["artifacts"] == {"track_id": "t1"}


def test_completing_fixed_sequence_closes_job(fixed_sequence):
    job_id = state.state_create_job("seq-agent", "goal")
    for step in ("a", "b", "c"):
        state.state_update(job_id, step, "done")
    assert state.state_get(job_id)["status"] == "done"
    assert state.state_list_open() == []
    assert len(state.state_list_closed()) == 1


def test_persists_across_engine_restart():
    job_id = state.state_create_job("dj-orchestrator", "goal")
    state.state_update(job_id, "intake", "done")
    state._engine = None  # simulate process restart
    assert [j["job_id"] for j in state.state_list_open()] == [job_id]


def test_failed_step_still_listed_for_resume():
    job_id = state.state_create_job("dj-orchestrator", "goal")
    state.state_update(job_id, "search", "failed", error="no results")
    jobs = state.state_list_open()
    assert jobs[0]["status"] == "failed" and jobs[0]["error"] == "no results"
    assert state.state_list_open(include_failed=False) == []
    assert state.state_resume(job_id)["status"] == "open"


def test_dynamic_agent_next_step_is_first_pending():
    job_id = state.state_create_job("set-builder", "goal")
    state.state_update(job_id, "track_1", "done")
    state.state_update(job_id, "track_2", "pending")
    assert state.state_get(job_id)["next_step"] == "track_2"


def test_dynamic_job_closed_by_complete():
    job_id = state.state_create_job("dj-orchestrator", "goal")
    state.state_update(job_id, "mix_1", "done")
    assert state.state_get(job_id)["status"] == "open"
    done = state.state_complete(job_id, {"track_id": "out-1"})
    assert done["status"] == "done" and done["result"] == {"track_id": "out-1"}


def test_unknown_job():
    with pytest.raises(KeyError):
        state.state_get("nope")


def test_request_input_parks_job_until_answered():
    job_id = state.state_create_job("dj-orchestrator", "goal")
    first = state.state_request_input(job_id, "style", "Mashup style?", ["Sequence", "Layered"], "Sequence")
    assert first == {"answered": False, "waiting": True}
    got = state.state_get(job_id)
    assert got["status"] == "waiting_input" and got["question"]["key"] == "style"
    assert [j["job_id"] for j in state.state_list_open()] == [job_id]  # waiting jobs are resumable

    state.state_answer(job_id, "style", "Layered")
    got = state.state_get(job_id)
    assert got["status"] == "open" and got["question"] is None
    # The resumed agent asks again and gets the stored answer, not a new question.
    again = state.state_request_input(job_id, "style", "Mashup style?", ["Sequence", "Layered"], "Sequence")
    assert again == {"answered": True, "answer": "Layered"}


def test_autopilot_takes_default_and_records_assumption():
    job_id = state.state_create_job("dj-orchestrator", "goal", {"autopilot": True})
    got = state.state_request_input(job_id, "style", "Mashup style?", ["Sequence", "Layered"], "Sequence")
    assert got["answered"] and got["answer"] == "Sequence" and got["autopilot"]
    job = state.state_get(job_id)
    assert job["status"] == "open" and job["question"] is None
    assert any("Sequence" in a for a in job["assumptions"])


def test_plan_and_assumptions_persist():
    job_id = state.state_create_job("dj-orchestrator", "goal")
    state.state_set_plan(job_id, {"mode": "sequence", "order": ["a", "b"]})
    state.state_add_assumption(job_id, "trending = current top 5")
    state.state_add_assumption(job_id, "trending = current top 5")  # no duplicates
    job = state.state_get(job_id)
    assert job["plan"]["order"] == ["a", "b"]
    assert job["assumptions"] == ["trending = current top 5"]
