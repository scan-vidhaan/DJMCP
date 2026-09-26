from __future__ import annotations

from fastapi import APIRouter, HTTPException

from djmcp.jobs import get_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def read_job(job_id: str) -> dict:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
