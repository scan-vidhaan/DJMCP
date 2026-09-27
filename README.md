# DJ MCP

An MCP server + FastAPI localhost app that turns Claude Code and GitHub Copilot into a DJ
assistant: search YouTube, download tracks, analyze, edit, apply effects and boosters, build
mashups and DJ sets, and control everything from a real-time web UI. All open source (MIT).

See [PLAN.md](<PLAN%20(1).md>) for the full build plan and phase-by-phase spec.

## Status

Under active development, built phase by phase. Currently: **Phase 3+4 — effects, boosters, mixing**.

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

### Analysis (BPM, key, sections)

`POST /api/analysis/analyze` (`{track_id, force?}`) runs `librosa`-based analysis: BPM, musical
key + Camelot notation (Krumhansl-Schmuckler profile matching), a beat grid, and section
boundaries with per-section energy (agglomerative clustering on MFCCs). Cached as a
`<track_id>.analysis.json` sidecar. Feeds the beat-snapping in `/api/edit/*` below.

### Editing (trim, split, section extraction)

- `POST /api/edit/trim` (`{track_id, start_sec, end_sec, snap_to_beat?}`) — cut a clip, snapped to
  the nearest analyzed beat by default.
- `POST /api/edit/split` (`{track_id, beat_indices}`) — cut a track into consecutive pieces at
  given beat-grid indices.
- `POST /api/edit/extract_section` (`{track_id, section}`) — pull out `"intro"`, `"drop"`,
  `"breakdown"`, or `"outro"` using analyzed section boundaries + energy (first/last sections are
  intro/outro; drop/breakdown are the highest/lowest-energy sections in between).

All editing outputs go to `storage/processed/` and can themselves be re-edited (trim a drop, then
trim that clip again) — track lookup checks both `storage/tracks/` and `storage/processed/`.

### Effects (reverb, filter, delay, EQ)

All in `djmcp/tools/effects.py`, `scipy.signal` + `numpy` only:

- `POST /api/fx/reverb` (`{track_id, room_size?, wet?}`) — Schroeder reverb (4 parallel combs into
  2 series allpasses).
- `POST /api/fx/filter` (`{track_id, type, cutoff_hz, resonance?}`) — lowpass/highpass/bandpass
  biquad (RBJ cookbook), `resonance` maps to Q.
- `POST /api/fx/delay` (`{track_id, time_ms?, feedback?, wet?}`) — feedback delay line.
- `POST /api/fx/eq` (`{track_id, low_gain?, mid_gain?, high_gain?}`) — 3-band shelf/peak/shelf.

Every effect peak-normalizes to -1 dBFS before export, so none of them can clip regardless of gain.

### Boosters (bass, vocal, energy)

- `POST /api/boost/bass` (`{track_id, gain_db?}`) — low-shelf boost via `apply_eq`.
- `POST /api/boost/energy` (`{track_id, amount?}`) — envelope-follower compressor + high-shelf +
  tanh saturation, one knob (`amount`) driving all three together.
- `POST /api/boost/vocal` (`{track_id, gain_db?}`) — demucs-isolates the vocal stem, boosts its
  gain, remixes. Always returns `{job_id}` (stem separation is always slow); poll
  `GET /api/jobs/{job_id}`.

### Mixing (crossfade, overlay_loop, mashup)

- `POST /api/mix/crossfade` (`{track_a, track_b, bars?}`) — beat-matches `track_b` to `track_a`'s
  BPM (if tempo drift < 10%), aligns first beats, linear amplitude crossfade over N bars.
- `POST /api/mix/overlay_loop` (`{track_id, loop_name, bars, start_beat?}`) — time-stretches a
  bundled loop (see `storage/loops/README.md` — all 15 are synthesized, not sampled, so there's no
  licensing question) to the track's BPM and layers it in.
- `POST /api/mix/mashup` (`{vocal_track, instrumental_track}`) — demucs-isolates the vocal,
  key-shifts it to the instrumental's key (±3 semitones max), aligns first beats, level-matches to
  -6 dBFS, mixes. Always returns `{job_id}`.

`vocal_boost` and `mashup` need the `demucs` stem-separation model, installed via the optional
`[boosters]` extra (`pip install -e ".[boosters]"`) — it pulls in PyTorch, a multi-GB install, so
it's opt-in rather than a base dependency.

## License

MIT — see [LICENSE](LICENSE).
