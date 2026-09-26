# DJ MCP

An MCP server + FastAPI localhost app that turns Claude Code and GitHub Copilot into a DJ
assistant: search YouTube, download tracks, analyze, edit, apply effects and boosters, build
mashups and DJ sets, and control everything from a real-time web UI. All open source (MIT).

See [PLAN.md](<PLAN%20(1).md>) for the full build plan and phase-by-phase spec.

## Status

Under active development, built phase by phase. Currently: **Phase 0 — scaffold**.

## Quickstart (dev)

```bash
py -3 -m venv .venv
./.venv/Scripts/activate
pip install -e .
python -m djmcp
```

Then `curl localhost:8000/health` should return `{"status": "ok", "version": "0.1.0"}`.

### ffmpeg

`pydub` and `yt-dlp` need `ffmpeg`. This repo uses a portable build under `bin/ffmpeg/` instead
of requiring a system-wide install — `djmcp/config.py` looks there first and falls back to
`ffmpeg` on `PATH`. To fetch it yourself:

```bash
curl -L https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip -o bin/ffmpeg.zip
# unzip into bin/ffmpeg/ so bin/ffmpeg/bin/ffmpeg.exe exists
```

## License

MIT — see [LICENSE](LICENSE).
