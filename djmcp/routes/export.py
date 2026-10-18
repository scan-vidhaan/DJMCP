from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import export

router = APIRouter(prefix="/api/export", tags=["export"])


class Mp3Request(BaseModel):
    track_id: str
    bitrate: int = 320


class ShortClipRequest(BaseModel):
    track_id: str
    duration: float = 30
    format: Literal["ig", "tiktok", "shorts"] = "ig"


@router.post("/mp3")
async def mp3(req: Mp3Request) -> dict:
    try:
        return await asyncio.to_thread(export.export_mp3, req.track_id, req.bitrate)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/short_clip")
async def short_clip(req: ShortClipRequest) -> dict:
    try:
        return await asyncio.to_thread(export.short_clip, req.track_id, req.duration, req.format)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
