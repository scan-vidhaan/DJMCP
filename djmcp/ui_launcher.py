"""Start the web server on demand and open the UI -- called by agents.

An agent running in a Claude Code chat calls open_ui so a non-technical user
never has to start the server or find the address themselves. If the UI is
already open in a browser (it pings the server every few seconds) no second
tab is opened.
"""

from __future__ import annotations

import subprocess
import sys
import time
import webbrowser

import requests

from djmcp.config import HOST, PORT, REPO_ROOT

BASE_URL = f"http://{HOST}:{PORT}"
STARTUP_TIMEOUT_SEC = 30


def server_is_up() -> bool:
    try:
        return requests.get(f"{BASE_URL}/health", timeout=1).ok
    except requests.RequestException:
        return False


def _start_server() -> None:
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "djmcp.server:app", "--host", HOST, "--port", str(PORT)],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def ui_is_open() -> bool:
    try:
        return bool(requests.get(f"{BASE_URL}/api/ui/status", timeout=1).json().get("open"))
    except (requests.RequestException, ValueError):
        return False


def open_ui(job_id: str | None = None) -> dict:
    """Make sure the server is running and the UI is on screen. Blocking."""
    started = False
    if not server_is_up():
        _start_server()
        started = True
        deadline = time.time() + STARTUP_TIMEOUT_SEC
        while time.time() < deadline and not server_is_up():
            time.sleep(0.5)
        if not server_is_up():
            raise RuntimeError(f"web server did not start on {BASE_URL} within {STARTUP_TIMEOUT_SEC}s")

    url = f"{BASE_URL}/#/job/{job_id}" if job_id else BASE_URL
    if job_id:  # an already-open UI follows this and jumps to the job
        try:
            requests.post(f"{BASE_URL}/api/ui/focus", json={"job_id": job_id}, timeout=2)
        except requests.RequestException:
            pass
    opened = False
    if not ui_is_open():
        opened = webbrowser.open(url)
    return {"url": url, "server_started": started, "browser_opened": bool(opened)}
