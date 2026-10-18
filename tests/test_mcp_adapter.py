from __future__ import annotations

import pytest

from djmcp.mcp_adapter.server import mcp

EXPECTED = {
    "search_song", "download_song", "analyze_track", "transcribe_track",
    "trim", "split_at_beats", "extract_section",
    "apply_reverb", "apply_filter", "apply_delay", "apply_eq",
    "bass_boost", "energy_lift", "vocal_boost",
    "crossfade", "overlay_loop", "mashup",
    "export_mp3", "short_clip", "get_job",
    "state_create_job", "state_update", "state_get", "state_list_open", "state_resume",
}


async def test_all_tools_registered_with_schemas():
    tools = {t.name: t for t in await mcp.list_tools()}
    assert EXPECTED <= set(tools)
    assert "track_id" in tools["analyze_track"].input_schema["properties"]


async def test_call_tool_end_to_end(synthetic_track):
    result = await mcp.call_tool("analyze_track", {"track_id": synthetic_track})
    # result shape varies by SDK version; just check the payload is there
    text = str(result)
    assert "bpm" in text
