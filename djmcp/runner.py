"""Runs the dj-orchestrator agent in the background for the web UI.

The UI never talks to a model itself. A request creates a job in the state
store, then this module starts `claude -p --agent dj-orchestrator` as a
subprocess with only the djmcp MCP tools allowed. The agent reports through
state_update / request_input; the UI polls the job record. When the agent
asks a question it stops; answering it (or resuming a failed job) starts a
fresh run on the same job, and the agent continues from its checkpoints.

Needs Claude Code installed and signed in on this machine. Override the
executable with DJMCP_CLAUDE_CMD (a full command line is allowed).
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from djmcp.config import REPO_ROOT
from djmcp.tools import state

logger = logging.getLogger(__name__)

AGENT_NAME = "dj-orchestrator"
ALLOWED_TOOLS = "mcp__djmcp,Agent"
MAX_LOG_EVENTS = 500

_procs: dict[str, subprocess.Popen] = {}
_logs: dict[str, list[dict]] = {}
_lock = threading.Lock()
# Jobs whose answer arrived while the previous run was still shutting down.
_resume_queued: set[str] = set()


class ClaudeNotFound(RuntimeError):
    pass


def claude_command() -> list[str]:
    override = os.environ.get("DJMCP_CLAUDE_CMD")
    if override:
        # posix=False (Windows paths with backslashes) keeps the quotes on tokens
        return [t.strip('"') for t in shlex.split(override, posix=(sys.platform != "win32"))]
    found = shutil.which("claude")
    if not found:
        raise ClaudeNotFound(
            "Claude Code was not found. Install it from https://claude.com/claude-code, "
            "sign in once, then restart this app."
        )
    return [found]


def claude_available() -> dict:
    try:
        return {"available": True, "command": claude_command()}
    except ClaudeNotFound as exc:
        return {"available": False, "error": str(exc)}


def _mcp_config_path() -> Path:
    """MCP config for the headless run. DJMCP_RUNNER=1 tells request_input not
    to block waiting for an answer: the run stops and is resumed instead."""
    config = {
        "mcpServers": {
            "djmcp": {
                "command": sys.executable,
                "args": ["-m", "djmcp.mcp_adapter"],
                "cwd": str(REPO_ROOT),
                "env": {"DJMCP_RUNNER": "1"},
            }
        }
    }
    path = Path(tempfile.gettempdir()) / "djmcp-runner-mcp.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def build_command(prompt: str) -> list[str]:
    return [
        *claude_command(),
        "-p",
        prompt,
        "--agent",
        AGENT_NAME,
        "--output-format",
        "stream-json",
        "--verbose",
        "--mcp-config",
        str(_mcp_config_path()),
        "--strict-mcp-config",
        "--allowedTools",
        ALLOWED_TOOLS,
    ]


def start_prompt(job_id: str, goal: str, autopilot: bool) -> str:
    return (
        f"{goal}\n\n"
        f"[job_id={job_id}] [autopilot={'on' if autopilot else 'off'}] [source=ui]\n"
        "The web UI already created this job. Use this job_id; do not create another."
    )


def resume_prompt(job_id: str) -> str:
    return (
        f"Resume job_id={job_id} [source=ui]. The user may have just answered your question. "
        "Call state_get and continue from next_step."
    )


def _log(job_id: str, event: dict) -> None:
    with _lock:
        events = _logs.setdefault(job_id, [])
        events.append(event)
        if len(events) > MAX_LOG_EVENTS:
            del events[: len(events) - MAX_LOG_EVENTS]


def get_log(job_id: str, since: int = 0) -> dict:
    with _lock:
        events = _logs.get(job_id, [])
        return {"events": events[since:], "next": len(events), "running": is_running(job_id)}


def is_running(job_id: str) -> bool:
    proc = _procs.get(job_id)
    return proc is not None and proc.poll() is None


def _handle_line(job_id: str, line: str) -> None:
    try:
        event = json.loads(line)
    except ValueError:
        return
    kind = event.get("type")
    if kind == "assistant":
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                _log(job_id, {"kind": "say", "text": block["text"].strip()})
            elif block.get("type") == "tool_use":
                _log(job_id, {"kind": "tool", "name": block.get("name", "")})
    elif kind == "result":
        _log(job_id, {"kind": "result", "text": str(event.get("result", "")), "error": bool(event.get("is_error"))})


def _watch(job_id: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        _handle_line(job_id, line)
    code = proc.wait()
    stderr_tail = (proc.stderr.read() if proc.stderr else "")[-500:].strip()

    if _procs.get(job_id) is not proc:  # a newer run already owns this job
        return
    with _lock:
        queued = job_id in _resume_queued
        _resume_queued.discard(job_id)
    if queued:  # the user answered while this run was exiting: continue now
        _spawn(job_id, resume_prompt(job_id))
        return

    try:
        job = state.state_get(job_id)
    except KeyError:
        return
    continued = (job.get("result") or {}).get("continued_job")
    if job["status"] == "done" and continued:
        # The user chose to continue an earlier job instead of this new one:
        # hand the work back to that job's own run.
        resume(continued)
        return
    if job["status"] in ("done", "waiting_input", "failed"):
        return
    if code != 0:
        reason = f"the assistant stopped unexpectedly (exit {code}). {stderr_tail}".strip()
    else:
        reason = "the assistant stopped before finishing. Press Resume to continue."
    state.state_update(job_id, "agent_run", "failed", error=reason)
    _log(job_id, {"kind": "result", "text": reason, "error": True})


def _spawn(job_id: str, prompt: str) -> None:
    if is_running(job_id):
        return
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    proc = subprocess.Popen(
        build_command(prompt),
        cwd=REPO_ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    _procs[job_id] = proc
    threading.Thread(target=_watch, args=(job_id, proc), daemon=True).start()


def start(goal: str, autopilot: bool = False) -> str:
    """Create a job for the request and start the orchestrator on it."""
    claude_command()  # fail fast, before a job is created, if Claude Code is missing
    job_id = state.state_create_job(AGENT_NAME, goal, {"autopilot": autopilot})
    _spawn(job_id, start_prompt(job_id, goal, autopilot))
    return job_id


def resume(job_id: str) -> None:
    state.state_resume(job_id)
    with _lock:
        if is_running(job_id):
            _resume_queued.add(job_id)
            return
    _spawn(job_id, resume_prompt(job_id))


def cancel(job_id: str) -> None:
    proc = _procs.get(job_id)
    if proc is not None and proc.poll() is None:
        proc.terminate()
    state.state_update(job_id, "agent_run", "failed", error="cancelled by the user")
