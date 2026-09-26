from __future__ import annotations

import asyncio

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from djmcp.jobs import complete_job, create_job, fail_job, update_progress
from djmcp.tools import youtube

router = APIRouter(prefix="/api/youtube", tags=["youtube"])

BACKGROUND_THRESHOLD_SEC = 10 * 60


class SearchRequest(BaseModel):
    query: str
    limit: int = 5


class DownloadRequest(BaseModel):
    url: str


@router.post("/search")
async def search(req: SearchRequest) -> list[dict]:
    return await youtube.search_song(req.query, req.limit)


def _run_download(job_id: str, url: str) -> None:
    def hook(d: dict) -> None:
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded / total * 100) if total else 0
            update_progress(job_id, percent, "downloading")
        elif d.get("status") == "finished":
            update_progress(job_id, 95, "converting")

    try:
        result = youtube.download_song(url, progress_hook=hook)
        complete_job(job_id, result)
    except Exception as exc:
        fail_job(job_id, str(exc))


@router.post("/download")
async def download(req: DownloadRequest, background_tasks: BackgroundTasks) -> dict:
    duration = 0
    try:
        duration = await youtube.probe_duration(req.url)
    except Exception:
        pass

    if duration > BACKGROUND_THRESHOLD_SEC:
        job_id = create_job()
        background_tasks.add_task(_run_download, job_id, req.url)
        return {"job_id": job_id}

    return await asyncio.to_thread(youtube.download_song, req.url)
