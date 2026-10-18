"""Entry point: python -m djmcp

Starts the web app and opens it in the browser. Set DJMCP_NO_BROWSER=1 to
skip opening a tab, DJMCP_RELOAD=1 for auto-reload while developing.
"""

import os
import threading
import webbrowser

import uvicorn

from djmcp.config import HOST, PORT


def main() -> None:
    if not os.environ.get("DJMCP_NO_BROWSER"):
        threading.Timer(1.5, webbrowser.open, args=(f"http://{HOST}:{PORT}",)).start()
    uvicorn.run("djmcp.server:app", host=HOST, port=PORT, reload=bool(os.environ.get("DJMCP_RELOAD")))


if __name__ == "__main__":
    main()
