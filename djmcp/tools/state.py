"""SQLite-backed job/step store so agent work survives a killed session.

Jobs are opened by the orchestrator (or the UI runner), steps are upserted
by specialist agents after each meaningful action, and state_get computes
which step is next. The same record carries what the UI shows: the chosen
plan, the assumptions the agents made, the pending question (if any) and
the final result.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, create_engine, select

from djmcp import config

# Optional fixed step sequences per agent name, used to compute next_step and
# to auto-close a job when the last step is done. Agents whose steps depend on
# the request (how many songs, how many transitions) are dynamic: next_step is
# then the first step not yet done, and the agent closes the job itself with
# state_complete.
AGENT_STEPS: dict[str, list[str]] = {}

OPEN_STATUSES = ("open", "waiting_input", "failed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True)
    agent: str
    goal: str
    params: str = "{}"  # JSON; params["autopilot"] suppresses questions
    status: str = "open"  # open | waiting_input | done | failed
    error: str | None = None
    plan: str = "null"  # JSON: the combination/plan the agents chose
    assumptions: str = "[]"  # JSON list of strings
    question: str = "null"  # JSON: the pending question, if any
    answers: str = "{}"  # JSON: key -> answer, for questions already settled
    result: str = "null"  # JSON: final output (track_id, path, ...)
    resumed_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class JobStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True)
    step: str
    status: str = "pending"  # pending | done | failed
    artifacts: str = "{}"  # JSON
    updated_at: datetime = Field(default_factory=_now)


_engine = None
_engine_path = None


def _get_engine():
    # Re-created if config.STATE_DB_PATH changes (tests point it at tmp_path).
    global _engine, _engine_path
    if _engine is None or _engine_path != config.STATE_DB_PATH:
        _engine = create_engine(f"sqlite:///{config.STATE_DB_PATH}")
        _engine_path = config.STATE_DB_PATH
        SQLModel.metadata.create_all(_engine)
    return _engine


def _next_step(job: Job, steps: list[JobStep]) -> str | None:
    by_name = {s.step: s for s in steps}
    sequence = AGENT_STEPS.get(job.agent)
    if sequence:
        for name in sequence:
            if name not in by_name or by_name[name].status != "done":
                return name
        return None
    for s in steps:
        if s.status != "done":
            return s.step
    return None


def _serialize(session: Session, job: Job) -> dict:
    steps = session.exec(select(JobStep).where(JobStep.job_id == job.id).order_by(JobStep.id)).all()
    return {
        "job_id": job.id,
        "agent": job.agent,
        "goal": job.goal,
        "params": json.loads(job.params),
        "status": job.status,
        "error": job.error,
        "plan": json.loads(job.plan),
        "assumptions": json.loads(job.assumptions),
        "question": json.loads(job.question),
        "answers": json.loads(job.answers),
        "result": json.loads(job.result),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "resumed_at": job.resumed_at.isoformat() if job.resumed_at else None,
        "steps": [
            {"step": s.step, "status": s.status, "artifacts": json.loads(s.artifacts)} for s in steps
        ],
        "next_step": _next_step(job, steps),
    }


def _require(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(f"no job found for job_id={job_id!r}")
    return job


def _save(session: Session, job: Job) -> dict:
    job.updated_at = _now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return _serialize(session, job)


def state_create_job(agent: str, goal: str, params: dict | None = None) -> str:
    job = Job(id=uuid.uuid4().hex[:12], agent=agent, goal=goal, params=json.dumps(params or {}))
    with Session(_get_engine()) as session:
        session.add(job)
        session.commit()
        return job.id


def state_update(
    job_id: str,
    step: str,
    status: str,
    artifacts: dict | None = None,
    error: str | None = None,
) -> dict:
    """Upsert a step. A failed step fails the job; finishing the last expected
    step of a fixed-sequence agent marks it done. Artifacts merge into any
    already stored for the step."""
    if status not in ("pending", "done", "failed"):
        raise ValueError(f"status must be pending|done|failed, got {status!r}")
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        row = session.exec(select(JobStep).where(JobStep.job_id == job_id, JobStep.step == step)).first()
        if row is None:
            row = JobStep(job_id=job_id, step=step)
        row.status = status
        row.artifacts = json.dumps({**json.loads(row.artifacts), **(artifacts or {})})
        row.updated_at = _now()
        session.add(row)
        session.flush()

        if status == "failed":
            job.status = "failed"
            job.error = error or f"step {step!r} failed"
        elif status == "done":
            if job.status == "failed":  # a retried step reopens a failed job
                job.status = "open"
                job.error = None
            steps = session.exec(select(JobStep).where(JobStep.job_id == job_id)).all()
            if job.agent in AGENT_STEPS and _next_step(job, steps) is None:
                job.status = "done"
        return _save(session, job)


def state_get(job_id: str) -> dict:
    with Session(_get_engine()) as session:
        return _serialize(session, _require(session, job_id))


def state_list_open(agent: str | None = None, include_failed: bool = True) -> list[dict]:
    """Unfinished jobs, newest first. Failed jobs are included by default
    because they are exactly the ones worth resuming."""
    statuses = OPEN_STATUSES if include_failed else ("open", "waiting_input")
    with Session(_get_engine()) as session:
        query = select(Job).where(Job.status.in_(statuses)).order_by(Job.updated_at.desc())
        if agent:
            query = query.where(Job.agent == agent)
        return [_serialize(session, j) for j in session.exec(query).all()]


def state_list_closed(limit: int = 50) -> list[dict]:
    with Session(_get_engine()) as session:
        query = select(Job).where(Job.status == "done").order_by(Job.updated_at.desc()).limit(limit)
        return [_serialize(session, j) for j in session.exec(query).all()]


def state_resume(job_id: str) -> dict:
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        job.resumed_at = _now()
        if job.status == "failed":
            job.status = "open"
            job.error = None
        return _save(session, job)


def state_set_plan(job_id: str, plan: dict) -> dict:
    """Store the chosen plan so a resumed run does not re-plan."""
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        job.plan = json.dumps(plan)
        return _save(session, job)


def state_add_assumption(job_id: str, text: str) -> dict:
    """Record a decision the agents made on the user's behalf; shown on the result page."""
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        items = json.loads(job.assumptions)
        if text not in items:
            items.append(text)
        job.assumptions = json.dumps(items)
        return _save(session, job)


def state_request_input(
    job_id: str,
    key: str,
    prompt: str,
    options: list[str] | None = None,
    default: str | None = None,
) -> dict:
    """Ask the user a question through the UI.

    `key` names the decision ("style", "resume_old_job"). Returns
    {"answered": True, "answer": ...} when the answer is already known
    (asked before, or the job runs in autopilot and `default` is taken);
    otherwise parks the job as waiting_input and returns {"answered": False}
    -- the agent should then stop and let the runner resume it once the user
    answers.
    """
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        answers = json.loads(job.answers)
        if key in answers:
            return {"answered": True, "answer": answers[key]}

        if json.loads(job.params).get("autopilot"):
            answers[key] = default
            job.answers = json.dumps(answers)
            assumptions = json.loads(job.assumptions)
            assumptions.append(f"{prompt} -> {default} (autopilot)")
            job.assumptions = json.dumps(assumptions)
            _save(session, job)
            return {"answered": True, "answer": default, "autopilot": True}

        job.question = json.dumps(
            {"key": key, "prompt": prompt, "options": options or [], "default": default}
        )
        job.status = "waiting_input"
        _save(session, job)
        return {"answered": False, "waiting": True}


def state_answer(job_id: str, key: str, answer: str) -> dict:
    """Record the user's answer (UI) and reopen the job."""
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        answers = json.loads(job.answers)
        answers[key] = answer
        job.answers = json.dumps(answers)
        job.question = "null"
        if job.status == "waiting_input":
            job.status = "open"
        return _save(session, job)


def state_complete(job_id: str, result: dict | None = None) -> dict:
    """Close a job as done with its final output."""
    with Session(_get_engine()) as session:
        job = _require(session, job_id)
        job.status = "done"
        job.error = None
        job.question = "null"
        job.result = json.dumps(result or {})
        return _save(session, job)
