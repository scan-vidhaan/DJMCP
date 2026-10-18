"""MCP (stdio) server exposing every djmcp tool.

Same functions the REST routes call -- this layer only adapts signatures.
Tools that block (librosa, pydub, yt-dlp) run in a worker thread so the
stdio event loop stays responsive. Slow ones (mashup, vocal_boost) return a
job_id immediately; poll it with get_job.

stdout is the protocol channel: nothing here may print to it.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Awaitable, Literal

from mcp.server.mcpserver import MCPServer

from djmcp import ui_launcher
from djmcp.jobs import complete_job, create_job, fail_job, get_job as _get_job
from djmcp.tools import (
    analysis,
    boosters,
    edit,
    effects,
    export,
    mix,
    planner,
    quality,
    state,
    transcribe,
    trending,
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


@mcp.tool()
async def find_trending(region: str = "India", genre: str = "Bollywood", limit: int = 8) -> dict:
    """Search current charts for a region and genre. Returns chart-page hits with text excerpts;
    read them, pick the actual song titles, then call search_song for each."""
    return await trending.find_trending(region, genre, limit)


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
async def mashup(
    vocal_track_id: str,
    instrumental_track_id: str,
    vocal_start_sec: float | None = None,
    vocal_end_sec: float | None = None,
) -> dict:
    """Vocals of one song over the instrumental of another: key-shifted, tempo-matched, entering one
    bar in with fades, edges snapped to lyric lines when the vocal track was transcribed.
    vocal_start_sec/vocal_end_sec choose which part of the vocal song to use (default all).
    Slow (demucs on both tracks): returns {job_id}; poll get_job."""
    return _start_job(mix.mashup(vocal_track_id, instrumental_track_id, vocal_start_sec, vocal_end_sec))


@mcp.tool()
async def medley(track_ids: list[str], bars: int = 8) -> dict:
    """Chain 2+ tracks in order with a beat-matched crossfade between each pair
    (short blend for pairs more than 10% apart in tempo). Returns the result plus transitions."""
    return await asyncio.to_thread(mix.medley, track_ids, bars)


@mcp.tool()
def plan_mixes(
    track_ids: list[str],
    mode: Literal["sequence", "layered", "both"] = "both",
    top_k: int = 4,
    titles: dict[str, str] | None = None,
) -> dict:
    """Rank ways to combine 2+ analyzed tracks (Camelot key fit, tempo gap, energy flow).
    mode: sequence (A then B then C), layered (one vocal over another instrumental) or both
    (layered opening, then the rest in sequence). Returns {plans:[{id, summary, score, reason, steps}]}."""
    return planner.plan_mixes(track_ids, mode, top_k, titles)


@mcp.tool()
async def check_seams(track_id: str, threshold_db: float = 9.0) -> dict:
    """Find abrupt level jumps (hard cuts, clipped entries) in a finished mix. {passed, jumps[]}."""
    return await asyncio.to_thread(quality.check_seams, track_id, threshold_db)


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
async def wait_for_job(job_id: str, timeout_sec: int = 60) -> dict:
    """Wait up to timeout_sec (max 120) for a background job (mashup, vocal_boost) to finish.
    Returns the job; if status is still pending/running, call again."""
    for _ in range(max(1, min(timeout_sec, 120)) // 2):
        job = _get_job(job_id)
        if job is None:
            raise ValueError(f"no job found for job_id={job_id!r}")
        if job["status"] in ("done", "failed"):
            return job
        await asyncio.sleep(2)
    return _get_job(job_id)


@mcp.tool()
def list_loops() -> list[dict]:
    """Bundled drum/808 loops usable with overlay_loop: [{name, bpm, bars}]."""
    return [{"name": m["name"], "bpm": m["bpm"], "bars": m["bars"]} for m in mix._manifest()]


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


@mcp.tool()
def state_set_plan(job_id: str, plan: dict) -> dict:
    """Save the chosen plan (mode, order, per-pair reasons) so a resumed run does not re-plan."""
    return state.state_set_plan(job_id, plan)


@mcp.tool()
def state_add_assumption(job_id: str, text: str) -> dict:
    """Record a decision made for the user (shown on the result page), e.g. 'trending = top 6 on current charts'."""
    return state.state_add_assumption(job_id, text)


@mcp.tool()
def state_complete(job_id: str, result: dict | None = None) -> dict:
    """Close the job as done. result should include track_id and path of the final output."""
    return state.state_complete(job_id, result)


ANSWER_WAIT_SEC = 600


@mcp.tool()
async def request_input(
    job_id: str,
    key: str,
    prompt: str,
    options: list[str] | None = None,
    default: str | None = None,
) -> dict:
    """Ask the user a question in the web UI. key names the decision (e.g. "style"); always give a default.
    Returns {answered: true, answer} when known (asked before, or autopilot took the default).
    If {answered: false}: stop and end your turn; you are resumed after the user answers."""
    result = state.state_request_input(job_id, key, prompt, options, default)
    if result["answered"] or os.environ.get("DJMCP_RUNNER") == "1":
        return result

    # Running in a chat session (not the UI runner): nothing will resume us,
    # so show the question in the UI and wait here for the answer.
    await asyncio.to_thread(ui_launcher.open_ui, job_id)
    for _ in range(ANSWER_WAIT_SEC // 2):
        await asyncio.sleep(2)
        answers = state.state_get(job_id)["answers"]
        if key in answers:
            return {"answered": True, "answer": answers[key]}
    return {"answered": False, "waiting": True, "timed_out": True}


@mcp.tool()
async def open_ui(job_id: str | None = None) -> dict:
    """Start the web UI if needed and show it to the user (jumps to job_id if given).
    Call this first when a user is chatting with you, so they can watch progress and answer questions there."""
    return await asyncio.to_thread(ui_launcher.open_ui, job_id)


def main() -> None:
    mcp.run(transport="stdio")
