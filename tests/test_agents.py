"""The agent and skill files are code too: a typo'd tool name silently gives an
agent a missing capability. Check them against the real MCP server."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from djmcp.config import REPO_ROOT
from djmcp.mcp_adapter.server import mcp

AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

AUDIO_TOOLS = {
    "search_song", "download_song", "analyze_track", "transcribe_track", "trim", "split_at_beats",
    "extract_section", "apply_reverb", "apply_filter", "apply_delay", "apply_eq", "bass_boost",
    "energy_lift", "vocal_boost", "crossfade", "overlay_loop", "mashup", "medley", "export_mp3",
    "short_clip", "find_trending",
}


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path.name} has no frontmatter"
    return yaml.safe_load(match.group(1))


def agent_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))


def skill_names() -> set[str]:
    return {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}


def tool_list(meta: dict) -> list[str]:
    # split on commas that are not inside Agent(...)
    return [t.strip() for t in re.split(r",\s*(?![^()]*\))", meta["tools"]) if t.strip()]


def test_expected_agents_and_skills_exist():
    assert {p.stem for p in agent_files()} == {"dj-orchestrator", "track-scout", "mashup-builder", "set-builder", "finisher"}
    assert skill_names() == {
        "state-management", "ask-policy", "remix-planner", "smooth-transitions",
        "harmonic-mixing", "mashup-recipe", "energy-arc", "beat-snapping",
    }


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
def test_agent_frontmatter_is_complete(path):
    meta = frontmatter(path)
    assert meta["name"] == path.stem
    assert meta["description"] and meta["tools"] and meta["model"]


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
async def test_agent_tools_exist_on_the_mcp_server(path):
    available = {t.name for t in await mcp.list_tools()}
    for tool in tool_list(frontmatter(path)):
        if tool.startswith("mcp__djmcp__"):
            assert tool.removeprefix("mcp__djmcp__") in available, f"{path.stem}: unknown tool {tool}"
        else:
            assert tool.startswith("Agent"), f"{path.stem}: unexpected non-djmcp tool {tool}"


@pytest.mark.parametrize("path", agent_files(), ids=lambda p: p.stem)
def test_agent_skills_exist(path):
    for skill in frontmatter(path).get("skills", []):
        assert skill in skill_names(), f"{path.stem}: unknown skill {skill}"


def test_orchestrator_has_no_audio_tools_and_spawns_only_known_agents():
    tools = tool_list(frontmatter(AGENTS_DIR / "dj-orchestrator.md"))
    assert not {t.removeprefix("mcp__djmcp__") for t in tools} & AUDIO_TOOLS
    spawn = next(t for t in tools if t.startswith("Agent("))
    spawned = {n.strip() for n in spawn[len("Agent("):-1].split(",")}
    assert spawned == {"track-scout", "mashup-builder", "set-builder", "finisher"}


def test_ask_capabilities_match_the_ask_policy():
    # only the orchestrator and the builders may ask; scout and finisher decide alone
    can_ask = {p.stem for p in agent_files() if "mcp__djmcp__request_input" in tool_list(frontmatter(p))}
    assert can_ask == {"dj-orchestrator", "mashup-builder", "set-builder"}


@pytest.mark.parametrize("name", sorted(skill_names()))
def test_skill_frontmatter(name):
    meta = frontmatter(SKILLS_DIR / name / "SKILL.md")
    assert meta["name"] == name and meta["description"]
