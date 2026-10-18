"""FastAPI app entry point for the DJ MCP server."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from djmcp import __version__
from djmcp.config import REPO_ROOT
from djmcp.routes import (
    analysis,
    boost,
    edit,
    export,
    fx,
    jobs,
    library,
    mix,
    requests,
    state,
    transcribe,
    youtube,
)

app = FastAPI(title="DJ MCP", version=__version__)

app.include_router(youtube.router)
app.include_router(jobs.router)
app.include_router(transcribe.router)
app.include_router(analysis.router)
app.include_router(edit.router)
app.include_router(fx.router)
app.include_router(boost.router)
app.include_router(mix.router)
app.include_router(export.router)
app.include_router(state.router)
app.include_router(requests.router)
app.include_router(library.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


# Last, so every /api route wins over the static catch-all.
_WEB_DIR = REPO_ROOT / "web"
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
