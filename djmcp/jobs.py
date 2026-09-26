"""In-process async job registry for long-running tool calls.

Not persistent — for durable, resumable agent state see djmcp/tools/state.py
(added in phase 5.5). This registry is only for tracking progress of a single
background operation (e.g. a slow download) within the life of the server
process.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Job:
    id: str
    status: str = "pending"  # pending | running | done | failed
    percent: int = 0
    message: str = ""
    result: Any = None
    error: str | None = None


_jobs: dict[str, Job] = {}


def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    _jobs[job_id] = Job(id=job_id)
    return job_id


def update_progress(job_id: str, percent: int, message: str = "") -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job.status = "running"
    job.percent = percent
    job.message = message


def complete_job(job_id: str, result: Any = None) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job.status = "done"
    job.percent = 100
    job.result = result


def fail_job(job_id: str, error: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job.status = "failed"
    job.error = error


def get_job(job_id: str) -> dict | None:
    job = _jobs.get(job_id)
    return asdict(job) if job is not None else None
