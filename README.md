# DJ MCP

An MCP server + FastAPI localhost app that turns Claude Code and GitHub Copilot into a DJ
assistant: search YouTube, download tracks, analyze, edit, apply effects and boosters, build
mashups and DJ sets, and control everything from a real-time web UI. All open source (MIT).

See [PLAN.md](<PLAN%20(1).md>) for the full build plan and phase-by-phase spec.

## Status

Under active development, built phase by phase. Currently: **Phase 1 — YouTube tools**.

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

### Search (Firecrawl, DuckDuckGo fallback)

`search_song` finds a song's YouTube URL via a Firecrawl web search restricted to
`site:youtube.com`, falling back to DuckDuckGo only if Firecrawl comes back empty. yt-dlp's own
`ytsearch` is deliberately not used for discovery — its extractor can stall for minutes on a
single request (rate-limiting, signature challenges) independent of network speed, which made it
an unreliable primary path. yt-dlp is still used for the actual download once a URL is known.

Firecrawl works out of the box with no API key (its rate-limited "keyless" tier). For higher
limits, set:

```bash
export FIRECRAWL_API_KEY=fc-your-key   # optional
```

### Transcription (lyrics with timestamps)

`POST /api/analysis/transcript` (`{track_id, model_size?, language?, force?}`) transcribes a
downloaded track with `faster-whisper`, giving segment- and word-level timestamps so the
orchestrating agent can reason about *what* is happening at a given point in a track (e.g. "the
hook lands at 34s") rather than only BPM/energy. Runs on the full mix, not an isolated vocal
stem — accuracy on instrumental-heavy sections is limited until vocal isolation (demucs) lands in
a later phase. Cached as a `<track_id>.transcript.json` sidecar next to the track.

## License

MIT — see [LICENSE](LICENSE).
