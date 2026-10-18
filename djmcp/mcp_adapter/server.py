"""MCP (stdio) server exposing every djmcp tool.

Same functions the REST routes call -- this layer only adapts signatures.
Tools that block (librosa, pydub, yt-dlp) run in a worker thread so the
stdio event loop stays responsive. Slow ones (mashup, vocal_boost) return a
job_id immediately; poll it with get_job.

stdout is the protocol channel: nothing here may print to it.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Literal

from mcp.server.mcpserver import MCPServer

from djmcp.jobs import complete_job, create_job, fail_job, get_job as _get_job
from djmcp.tools import (
    analysis,
    boosters,
    edit,
    effects,
    export,
    mix,
    state,
    transcribe,
    youtube,
)

mcp = MCPServer("djmcp")

# Strong refs so fire-and-forget job tasks aren't garbage-collected mid-run.
_background: set[asyncio.Task] = set()


def _start_job(coro: Awaitable[Any]) -> dict:
    job_id = create_job()

    async def runner() -> None:
        try:
            complete_job(job_id, await coro)
        except Exception as exc:  # surfaced to the caller via get_job
            fail_job(job_id, f"{type(exc).__name__}: {exc}")

    task = asyncio.create_task(runner())
    _background.add(task)
    task.add_done_callback(_background.discard)
    return {"job_id": job_id}


# --- Discovery ---------------------------------------------------------------


@mcp.tool()
async def search_song(query: str, limit: int = 5) -> list[dict]:
    """Search YouTube for a song. Returns [{title, url, duration, uploader, source}]."""
    return await youtube.search_song(query, limit)


@mcp.tool()
async def download_song(url: str) -> dict:
    """Download a YouTube URL as a 320kbps mp3. Returns {track_id, path, title, duration}."""
    return await asyncio.to_thread(youtube.download_song, url)


# --- Understanding -----------------------------------------------------------


@mcp.tool()
async def analyze_track(track_id: str, force: bool = False) -> dict:
    """BPM, key, Camelot code, beat times, sections with energy. Cached per track."""
    return await asyncio.to_thread(analysis.analyze_track, track_id, force)


@mcp.tool()
async def transcribe_track(track_id: str, language: str | None = None, force: bool = False) -> dict:
    """Timestamped lyrics via whisper. Pass an ISO 639-1 language code (e.g. "kn") when auto-detect is unreliable."""
    return await transcribe.transcribe_track(track_id, language=language, force=force)


# --- Editing -----------------------------------------------------------------


@mcp.tool()
async def trim(track_id: str, start_sec: float, end_sec: float, snap_to_beat: bool = True) -> dict:
    """Cut [start_sec, end_sec) from a track, snapped to the nearest beats by default."""
    return await asyncio.to_thread(edit.trim, track_id, start_sec, end_sec, snap_to_beat)


@mcp.tool()
async def split_at_beats(track_id: str, beat_indices: list[int]) -> list[dict]:
    """Split a track into consecutive pieces at the given beat-grid indices."""
    return await asyncio.to_thread(edit.split_at_beats, track_id, beat_indices)


@mcp.tool()
async def extract_section(track_id: str, section_name: Literal["intro", "drop", "breakdown", "outro"]) -> dict:
    """Extract the intro, drop (highest-energy middle section), breakdown (lowest) or outro."""
    return await asyncio.to_thread(edit.extract_section, track_id, section_name)


# --- Effects -----------------------------------------------------------------


@mcp.tool()
async def apply_reverb(track_id: str, room_size: float = 0.5, wet: float = 0.3) -> dict:
    """Schroeder reverb."""
    return await asyncio.to_thread(effects.apply_reverb, track_id, room_size, wet)


@mcp.tool()
async def apply_filter(
    track_id: str,
    type: Literal["lowpass", "highpass", "bandpass"],
    cutoff_hz: float,
    resonance: float = 0.7,
) -> dict:
    """Butterworth lowpass/highpass/bandpass filter."""
    return await asyncio.to_thread(effects.apply_filter, track_id, type, cutoff_hz, resonance)


@mcp.tool()
async def apply_delay(track_id: str, time_ms: float = 250.0, feedback: float = 0.3, wet: float = 0.3) -> dict:
    """Feedback delay."""
    return await asyncio.to_thread(effects.apply_delay, track_id, time_ms, feedback, wet)


@mcp.tool()
async def apply_eq(track_id: str, low_gain: float = 0.0, mid_gain: float = 0.0, high_gain: float = 0.0) -> dict:
    """3-band EQ; gains in dB."""
    return await asyncio.to_thread(effects.apply_eq, track_id, low_gain, mid_gain, high_gain)


# --- Boosters ----------------------------------------------------------------


@mcp.tool()
async def bass_boost(track_id: str, gain_db: float = 6.0) -> dict:
    """Low-shelf boost below ~200 Hz."""
    return await asyncio.to_thread(boosters.bass_boost, track_id, gain_db)


@mcp.tool()
async def energy_lift(track_id: str, amount: float = 0.5) -> dict:
    """Compressor + high-shelf + soft-clip saturation. amount in 0..1."""
    return await asyncio.to_thread(boosters.energy_lift, track_id, amount)


@mcp.tool()
async def vocal_boost(track_id: str, gain_db: float = 6.0) -> dict:
    """Demucs-isolate the vocal stem, gain it, remix. Slow: returns {job_id}; poll get_job."""
    return _start_job(boosters.vocal_boost(track_id, gain_db))


# --- Mixing ------------------------------------------------------------------


@mcp.tool()
async def crossfade(track_a_id: str, track_b_id: str, bars: int = 8) -> dict:
    """Beat-match track B to A and crossfade over N bars."""
    return await asyncio.to_thread(mix.crossfade, track_a_id, track_b_id, bars)


@mcp.tool()
async def overlay_loop(track_id: str, loop_name: str, bars: int, start_beat: int = 0) -> dict:
    """Layer a bundled drum/808 loop (see storage/loops/manifest.json) over a track, beat-aligned."""
    return await asyncio.to_thread(mix.overlay_loop, track_id, loop_name, bars, start_beat)


@mcp.tool()
async def mashup(vocal_track_id: str, instrumental_track_id: str) -> dict:
    """Vocals of one song over the instrumental of another, key-shifted and downbeat-aligned.
    Slow (demucs on both tracks): returns {job_id}; poll get_job."""
    return _start_job(mix.mashup(vocal_track_id, instrumental_track_id))


# --- Export ------------------------------------------------------------------


@mcp.tool()
async def export_mp3(track_id: str, bitrate: int = 320) -> dict:
    """Write the track to storage/exports/ at the given bitrate (kbps)."""
    return await asyncio.to_thread(export.export_mp3, track_id, bitrate)


@mcp.tool()
async def short_clip(track_id: str, duration: float = 30, format: Literal["ig", "tiktok", "shorts"] = "ig") -> dict:
    """Fade-in/out clip centered on the track's highest-energy section."""
    return await asyncio.to_thread(export.short_clip, track_id, duration, format)


# --- Jobs --------------------------------------------------------------------


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Status/progress/result of a background job started by mashup or vocal_boost."""
    job = _get_job(job_id)
    if job is None:
        raise ValueError(f"no job found for job_id={job_id!r}")
    return job


# --- State (agent checkpoints) -----------------------------------------------


@mcp.tool()
def state_create_job(agent: str, goal: str, params: dict | None = None) -> str:
    """Open a resumable agent job. Returns job_id."""
    return state.state_create_job(agent, goal, params)


@mcp.tool()
def state_update(
    job_id: str,
    step: str,
    status: Literal["pending", "done", "failed"],
    artifacts: dict | None = None,
    error: str | None = None,
) -> dict:
    """Checkpoint a step with the artifacts (track_ids, paths) later steps need."""
    return state.state_update(job_id, step, status, artifacts, error)


@mcp.tool()
def state_get(job_id: str) -> dict:
    """Full job state including completed steps and the computed next_step."""
    return state.state_get(job_id)


@mcp.tool()
def state_list_open(agent: str | None = None) -> list[dict]:
    """Unfinished (open or failed) jobs, newest first, for resumption."""
    return state.state_list_open(agent)


@mcp.tool()
def state_resume(job_id: str) -> dict:
    """Mark a job resumed and return its state; continue from next_step."""
    return state.state_resume(job_id)


def main() -> None:
    mcp.run(transport="stdio")
