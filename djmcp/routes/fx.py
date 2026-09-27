from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import effects

router = APIRouter(prefix="/api/fx", tags=["fx"])


class ReverbRequest(BaseModel):
    track_id: str
    room_size: float = 0.5
    wet: float = 0.3


class FilterRequest(BaseModel):
    track_id: str
    type: str
    cutoff_hz: float
    resonance: float = 0.7


class DelayRequest(BaseModel):
    track_id: str
    time_ms: float = 250.0
    feedback: float = 0.3
    wet: float = 0.3


class EqRequest(BaseModel):
    track_id: str
    low_gain: float = 0.0
    mid_gain: float = 0.0
    high_gain: float = 0.0


@router.post("/reverb")
async def reverb(req: ReverbRequest) -> dict:
    try:
        return await asyncio.to_thread(effects.apply_reverb, req.track_id, req.room_size, req.wet)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/filter")
async def filter_(req: FilterRequest) -> dict:
    try:
        return await asyncio.to_thread(
            effects.apply_filter, req.track_id, req.type, req.cutoff_hz, req.resonance
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delay")
async def delay(req: DelayRequest) -> dict:
    try:
        return await asyncio.to_thread(
            effects.apply_delay, req.track_id, req.time_ms, req.feedback, req.wet
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/eq")
async def eq(req: EqRequest) -> dict:
    try:
        return await asyncio.to_thread(
            effects.apply_eq, req.track_id, req.low_gain, req.mid_gain, req.high_gain
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
