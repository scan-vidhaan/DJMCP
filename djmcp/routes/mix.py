from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from djmcp.jobs import complete_job, create_job, fail_job
from djmcp.tools import mix

router = APIRouter(prefix="/api/mix", tags=["mix"])


class CrossfadeRequest(BaseModel):
    track_a: str
    track_b: str
    bars: int = 8


class OverlayLoopRequest(BaseModel):
    track_id: str
    loop_name: str
    bars: int
    start_beat: int = 0


class MashupRequest(BaseModel):
    vocal_track: str
    instrumental_track: str


@router.post("/crossfade")
async def crossfade(req: CrossfadeRequest) -> dict:
    try:
        return await asyncio.to_thread(mix.crossfade, req.track_a, req.track_b, req.bars)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/overlay_loop")
async def overlay_loop(req: OverlayLoopRequest) -> dict:
    try:
        return await asyncio.to_thread(
            mix.overlay_loop, req.track_id, req.loop_name, req.bars, req.start_beat
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _run_mashup(job_id: str, vocal_track: str, instrumental_track: str) -> None:
    try:
        result = asyncio.run(mix.mashup(vocal_track, instrumental_track))
        complete_job(job_id, result)
    except Exception as exc:
        fail_job(job_id, str(exc))


@router.post("/mashup")
async def mashup(req: MashupRequest, background_tasks: BackgroundTasks) -> dict:
    """demucs-based stem separation is always slow enough to warrant a background job."""
    job_id = create_job()
    background_tasks.add_task(_run_mashup, job_id, req.vocal_track, req.instrumental_track)
    return {"job_id": job_id}
