"""FastAPI app entry point for the DJ MCP server."""

from fastapi import FastAPI

from djmcp import __version__
from djmcp.routes import analysis, edit, jobs, transcribe, youtube

app = FastAPI(title="DJ MCP", version=__version__)

app.include_router(youtube.router)
app.include_router(jobs.router)
app.include_router(transcribe.router)
app.include_router(analysis.router)
app.include_router(edit.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}
