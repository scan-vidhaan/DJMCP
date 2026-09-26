from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from djmcp.tools import transcribe

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class TranscribeRequest(BaseModel):
    track_id: str
    model_size: str = transcribe.DEFAULT_MODEL_SIZE
    language: str | None = None
    force: bool = False


@router.post("/transcript")
async def transcript(req: TranscribeRequest) -> dict:
    try:
        return await transcribe.transcribe_track(
            req.track_id, req.model_size, req.language, req.force
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
