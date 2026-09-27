from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from djmcp.jobs import complete_job, create_job, fail_job
from djmcp.tools import boosters

router = APIRouter(prefix="/api/boost", tags=["boost"])


class BassRequest(BaseModel):
    track_id: str
    gain_db: float = 6.0


class VocalRequest(BaseModel):
    track_id: str
    gain_db: float = 6.0


class EnergyRequest(BaseModel):
    track_id: str
    amount: float = 0.5


@router.post("/bass")
async def bass(req: BassRequest) -> dict:
    try:
        return await asyncio.to_thread(boosters.bass_boost, req.track_id, req.gain_db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/energy")
async def energy(req: EnergyRequest) -> dict:
    try:
        return await asyncio.to_thread(boosters.energy_lift, req.track_id, req.amount)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _run_vocal_boost(job_id: str, track_id: str, gain_db: float) -> None:
    try:
        result = asyncio.run(boosters.vocal_boost(track_id, gain_db))
        complete_job(job_id, result)
    except Exception as exc:
        fail_job(job_id, str(exc))


@router.post("/vocal")
async def vocal(req: VocalRequest, background_tasks: BackgroundTasks) -> dict:
    """demucs-based stem separation is always slow enough to warrant a background job."""
    job_id = create_job()
    background_tasks.add_task(_run_vocal_boost, job_id, req.track_id, req.gain_db)
    return {"job_id": job_id}
