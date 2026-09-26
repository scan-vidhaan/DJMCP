from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    track_id: str
    force: bool = False


@router.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict:
    try:
        return await asyncio.to_thread(analysis.analyze_track, req.track_id, req.force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
