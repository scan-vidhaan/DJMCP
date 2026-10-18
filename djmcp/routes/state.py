from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import state

router = APIRouter(prefix="/api/state", tags=["state"])


class CreateJobRequest(BaseModel):
    agent: str
    goal: str
    params: dict = {}


class UpdateJobRequest(BaseModel):
    step: str
    status: str
    artifacts: dict | None = None
    error: str | None = None


@router.post("/jobs")
def create_job(req: CreateJobRequest) -> dict:
    return {"job_id": state.state_create_job(req.agent, req.goal, req.params)}


@router.get("/jobs")
def list_jobs(open: bool = True, agent: str | None = None) -> list[dict]:
    if open:
        return state.state_list_open(agent)
    return state.state_list_closed()


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return state.state_get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/jobs/{job_id}")
def update_job(job_id: str, req: UpdateJobRequest) -> dict:
    try:
        return state.state_update(job_id, req.step, req.status, req.artifacts, req.error)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str) -> dict:
    try:
        return state.state_resume(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
