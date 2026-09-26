"""FastAPI app entry point for the DJ MCP server."""

from fastapi import FastAPI

from djmcp import __version__

app = FastAPI(title="DJ MCP", version=__version__)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}
