from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import edit

router = APIRouter(prefix="/api/edit", tags=["edit"])


class TrimRequest(BaseModel):
    track_id: str
    start_sec: float
    end_sec: float
    snap_to_beat: bool = True


class SplitRequest(BaseModel):
    track_id: str
    beat_indices: list[int]


class ExtractSectionRequest(BaseModel):
    track_id: str
    section: str


@router.post("/trim")
async def trim(req: TrimRequest) -> dict:
    try:
        return await asyncio.to_thread(
            edit.trim, req.track_id, req.start_sec, req.end_sec, req.snap_to_beat
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/split")
async def split(req: SplitRequest) -> list[dict]:
    try:
        return await asyncio.to_thread(edit.split_at_beats, req.track_id, req.beat_indices)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/extract_section")
async def extract_section(req: ExtractSectionRequest) -> dict:
    try:
        return await asyncio.to_thread(edit.extract_section, req.track_id, req.section)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
