"""FastAPI app entry point for the DJ MCP server."""

from fastapi import FastAPI

from djmcp import __version__
from djmcp.routes import analysis, boost, edit, export, fx, jobs, mix, state, transcribe, youtube

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}
