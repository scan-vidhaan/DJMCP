"""Endpoints the web UI uses to start, steer and watch agent runs."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp import runner
from djmcp.tools import state

router = APIRouter(prefix="/api", tags=["requests"])

_ui_last_ping = 0.0
_ui_focus: dict = {"job_id": None, "seq": 0}
UI_OPEN_WINDOW_SEC = 15


class NewRequest(BaseModel):
    text: str
    autopilot: bool = False


class Answer(BaseModel):
    key: str
    answer: str


class Focus(BaseModel):
    job_id: str


def _require_job(job_id: str) -> dict:
    try:
        return state.state_get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/system/check")
def system_check() -> dict:
    return runner.claude_available()


@router.post("/requests")
def create_request(req: NewRequest) -> dict:
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Tell me what you'd like to make.")
    try:
        return {"job_id": runner.start(req.text.strip(), req.autopilot)}
    except runner.ClaudeNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/requests/{job_id}/log")
def request_log(job_id: str, since: int = 0) -> dict:
    _require_job(job_id)
    return runner.get_log(job_id, since)


@router.post("/requests/{job_id}/answer")
def answer(job_id: str, body: Answer) -> dict:
    _require_job(job_id)
    job = state.state_answer(job_id, body.key, body.answer)
    try:
        runner.resume(job_id)
    except runner.ClaudeNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return job


@router.post("/requests/{job_id}/resume")
def resume(job_id: str) -> dict:
    _require_job(job_id)
    try:
        runner.resume(job_id)
    except runner.ClaudeNotFound as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return state.state_get(job_id)


@router.post("/requests/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    _require_job(job_id)
    runner.cancel(job_id)
    return state.state_get(job_id)


@router.post("/ui/ping")
def ui_ping() -> dict:
    """The page calls this every few seconds so agents know the UI is open."""
    global _ui_last_ping
    _ui_last_ping = time.time()
    return {"ok": True}


@router.get("/ui/status")
def ui_status() -> dict:
    return {
        "open": time.time() - _ui_last_ping < UI_OPEN_WINDOW_SEC,
        "focus_job": _ui_focus["job_id"],
        "focus_seq": _ui_focus["seq"],
    }


@router.post("/ui/focus")
def ui_focus(body: Focus) -> dict:
    """An agent asks an already-open UI to jump to a job."""
    _ui_focus["job_id"] = body.job_id
    _ui_focus["seq"] += 1
    return {"ok": True}
