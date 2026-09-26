# DJ MCP — Full Build Plan

An MCP server + FastAPI localhost app that turns Claude Code and GitHub Copilot into a DJ assistant. Search YouTube, download tracks, analyze, edit, apply effects and boosters, build mashups and DJ sets, and control everything from a real-time web UI. All open source.

---

## 1. Vision

A single localhost application that exposes DJ tooling through three surfaces:

- **MCP server (stdio)** — Claude Code, GitHub Copilot, Cursor, and any other MCP client can call every tool.
- **REST API (localhost:8000)** — the web UI and any external script uses these.
- **WebSocket (/ws)** — live control from the web UI over **already-remixed / already-processed tracks** (browse the library of finished outputs, load into deck, scrub, apply live FX preview, mark cues, export). The web UI is a **post-production control surface**, not a generator — all generation happens through Claude Code / MCP.

Orchestration lives in **Claude Code custom subagents + skills** (Markdown files that ship with the repo), coordinated by a top-level **`dj-orchestrator`** subagent that routes user requests to specialist subagents and maintains per-job state. The server is a boring, stateless tool executor — no LLM calls, no orchestration logic inside it. State (job progress, agent checkpoints, resumable work) lives in a small SQLite file the subagents read/write via MCP.

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────┐
│  Claude Code / GHCP  ──MCP (stdio)──►                  │
│  Web UI (browser)    ──REST + WS───►   FastAPI server  │
│                                        localhost:8000  │
└────────────────────────────────────────────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        YouTube tools     Audio editor       Effects + Boosters
        (yt-dlp)          (pydub, librosa)   (scipy.signal, demucs)
              │                 │                 │
              └─────────────────┴─────────────────┘
                                │
                                ▼
                       storage/  (tracks, processed, loops)

Orchestration lives OUTSIDE the server:
  .claude/agents/*.md      — custom subagents:
                              dj-orchestrator (top-level router + state)
                              mashup-builder, set-builder, track-scout
  .claude/skills/*/SKILL.md — reusable procedures (harmonic-mixing, beat-snapping, ...)

State (resumable, per-job) lives in:
  storage/state.db          — SQLite, exposed via MCP tools:
                              state_create_job, state_update, state_get,
                              state_list_open, state_resume
```

---

## 3. Tech stack (all open source)

| Concern | Library | License | Notes |
|---|---|---|---|
| Web framework | FastAPI + Uvicorn | MIT | REST + WebSocket |
| MCP protocol | `mcp` (official Python SDK) | MIT | stdio transport |
| YouTube search + download | `yt-dlp` | Unlicense | `ytsearch{N}:` for search |
| Audio I/O + slicing | `pydub` | MIT | Needs ffmpeg |
| Analysis (BPM, key, beats) | `librosa` | ISC | Chroma + Krumhansl for key |
| Time-stretch + pitch-shift | `librosa.effects` | ISC | MIT-compatible |
| Effects (EQ, filter, reverb, delay) | `scipy.signal` + `numpy` | BSD-3 | MIT-compatible. Biquad filters, Schroeder/FDN reverb, delay line, shelving EQ — all hand-rolled |
| Stem separation | `demucs` | MIT | For vocal/instrumental splits |
| Web search fallback | `duckduckgo-search` | MIT | When yt-dlp search returns nothing usable |
| State store | `sqlite3` (stdlib) + `sqlmodel` | MIT | Job + agent state, resumable |
| Web UI | Vanilla JS + `wavesurfer.js` | MIT + BSD-3 | Waveform + scrub over processed outputs |
| Package/dep manager | `uv` | MIT | Fast installs |
| Tests | `pytest` | MIT | |

**Licensing note:** Whole stack is now MIT/BSD/ISC — no GPL surface, safe for permissive relicensing later. `scipy.signal` covers everything `pedalboard` would have done for v1: `iirfilter`/`sosfilt` for lowpass/highpass/bandpass, `lfilter` for delays and comb-based reverb, shelving via biquad coefficients, compressor as a hand-rolled envelope follower over numpy arrays.

---

## 4. Repository layout

```
dj-mcp/
├── pyproject.toml
├── README.md
├── PLAN.md                       # this file
├── djmcp/
│   ├── __init__.py
│   ├── config.py                 # paths, defaults, env
│   ├── server.py                 # FastAPI app entry
│   ├── mcp_adapter.py            # stdio MCP server exposing tools/*
│   ├── ws.py                     # WebSocket handlers
│   ├── jobs.py                   # in-process async job registry
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── youtube.py            # search_song (ytsearch), download_song
│   │   ├── web_search.py         # fallback: duckduckgo → resolve to YT link
│   │   ├── analysis.py           # analyze_track, detect_beats, detect_key
│   │   ├── edit.py               # trim, split_at_beats, extract_section
│   │   ├── effects.py            # reverb, filter, delay, eq (scipy.signal)
│   │   ├── boosters.py           # bass_boost, vocal_boost, energy_lift
│   │   ├── mix.py                # crossfade, overlay_loop, mashup
│   │   ├── export.py             # to_mp3, to_wav, short_clip
│   │   └── state.py              # SQLite job/agent state — resumable
│   └── storage/
│       ├── tracks/               # downloaded originals
│       ├── processed/            # remixed / finished outputs (what the web UI shows)
│       ├── loops/                # bundled royalty-free loops (CC0)
│       └── state.db              # SQLite state store
├── web/
│   ├── index.html
│   ├── app.js                    # wavesurfer + WS client (post-remix control only)
│   └── style.css
├── .claude/                      # ships with the repo, users copy or symlink
│   ├── agents/
│   │   ├── dj-orchestrator.md    # top-level router + state manager
│   │   ├── mashup-builder.md
│   │   ├── set-builder.md
│   │   └── track-scout.md
│   └── skills/
│       ├── mashup-recipe/SKILL.md
│       ├── beat-snapping/SKILL.md
│       ├── harmonic-mixing/SKILL.md
│       ├── energy-arc/SKILL.md
│       └── state-management/SKILL.md   # how agents checkpoint + resume
└── tests/
    ├── test_youtube.py
    ├── test_analysis.py
    ├── test_edit.py
    ├── test_effects.py
    └── test_mix.py
```

---

## 5. API surface

Every tool has both a **REST endpoint** and an **MCP tool binding**. Same function underneath.

### YouTube (`/api/youtube`)
- `POST /search` — `{query, limit}` → list of `{title, url, duration, uploader, source: "yt"|"web"}`
  - Tries `yt-dlp` `ytsearch{limit}:{query}` first (mimics a real user search).
  - **Fallback**: if the yt-dlp search returns 0 results, results all >30 min (likely mixes), or all uploader-mismatched, call `web_search.find_youtube(query)` which uses `duckduckgo-search` for `"{query} site:youtube.com"`, extracts YouTube URLs from results, then runs each through `yt-dlp` `--dump-json` to get real metadata. Marked `source: "web"` so the caller knows the path taken.
- `POST /download` — `{url}` → `{track_id, path, duration}` (async: returns job_id if long)

### Analysis (`/api/analysis`)
- `POST /analyze` — `{track_id}` → `{bpm, key, camelot, duration, beat_times, sections, energy}`
- `GET /tracks/{id}` — cached metadata

### Editing (`/api/edit`)
- `POST /trim` — `{track_id, start, end, snap_to_beat}` → new track_id
- `POST /split` — `{track_id, beat_indices}` → list of new track_ids
- `POST /extract_section` — `{track_id, section: "intro"|"drop"|"breakdown"|"outro"}` → new track_id

### Effects (`/api/fx`)
- `POST /reverb` — `{track_id, room_size, wet}`
- `POST /filter` — `{track_id, type: "lowpass"|"highpass"|"bandpass", cutoff, resonance}`
- `POST /delay` — `{track_id, time_ms, feedback, wet}`
- `POST /eq` — `{track_id, low_gain, mid_gain, high_gain}`

### Boosters (`/api/boost`)
- `POST /bass` — `{track_id, gain_db}`
- `POST /vocal` — `{track_id, gain_db}` (demucs split + gain vocal stem)
- `POST /energy` — `{track_id, amount}` (compressor + high-shelf + light saturation)

### Mix (`/api/mix`)
- `POST /crossfade` — `{track_a, track_b, bars}` → new track_id
- `POST /overlay_loop` — `{track_id, loop_name, bars, start_beat}` → new track_id
- `POST /mashup` — `{vocal_track, instrumental_track}` → new track_id

### Export (`/api/export`)
- `POST /mp3` — `{track_id, bitrate}` → file path + download URL
- `POST /short_clip` — `{track_id, duration, format: "ig"|"tiktok"|"shorts"}` → 30-60s clip centered on drop

### Jobs
- `GET /api/jobs/{job_id}` — status + progress
- `WS /ws/jobs/{job_id}` — streaming progress

### State (agent memory — resumable work)
- `POST /api/state/jobs` — `{agent, goal, params}` → `{job_id}` (opens a new agent-level job)
- `PATCH /api/state/jobs/{job_id}` — `{step, status, checkpoint, artifacts}` update a step
- `GET /api/state/jobs/{job_id}` — full state incl. completed steps + next step
- `GET /api/state/jobs?open=true&agent=mashup-builder` — list unfinished work for resumption
- `POST /api/state/jobs/{job_id}/resume` — mark as resumed (agent picks up from `next step`)

### Web UI control (post-remix only)
The web UI operates on `storage/processed/` — the library of finished remixes/mashups/sets.
- `GET /api/library/processed` — list of remixed outputs with metadata
- `WS /ws` — load a processed track into the browser deck, scrub, preview live FX (non-destructive), mark cue points, request an export. The UI does **not** call generation tools (mashup, set-builder, download); those go through Claude Code.

---

## 6. MCP tools exposed

Same names as REST, prefixed `mcp__djmcp__`. Long-running ops return a `job_id` and stream progress via MCP notifications.

Grouped for readability:

- **Discovery**: `search_song`, `download_song`
- **Understanding**: `analyze_track`
- **Editing**: `trim`, `split_at_beats`, `extract_section`
- **Effects**: `apply_reverb`, `apply_filter`, `apply_delay`, `apply_eq`
- **Boosters**: `bass_boost`, `vocal_boost`, `energy_lift`
- **Mixing**: `crossfade`, `overlay_loop`, `mashup`
- **Export**: `export_mp3`, `short_clip`
- **State**: `state_create_job`, `state_update`, `state_get`, `state_list_open`, `state_resume`

---

## 7. Claude Code integration (subagents + skills)

The `.claude/` folder ships with the repo. Users clone and either copy `.claude/` into their project or run Claude Code from the repo root.

### Subagents

**`.claude/agents/dj-orchestrator.md`** ⭐ (top-level)
- Purpose: single entry point for the user. Parses intent, opens a state job with `state_create_job`, delegates to the right specialist subagent, and on failure/interruption, picks up open jobs via `state_list_open`.
- Tools: `state_create_job`, `state_update`, `state_get`, `state_list_open`, `state_resume`, plus `Task` (to spawn other subagents).
- Uses skills: `state-management`.
- Rule: never calls audio tools directly — always delegates. This keeps the router thin and reasoning cheap.

**`.claude/agents/mashup-builder.md`**
- Purpose: build a beat-matched, key-compatible mashup from two songs.
- Tools: `search_song`, `download_song`, `analyze_track`, `mashup`, `export_mp3`, plus state tools (`state_update`, `state_get`).
- Uses skills: `mashup-recipe`, `harmonic-mixing`, `state-management`.
- Checkpoints each step (searched → downloaded → analyzed → mixed → exported) via `state_update` so a killed session can resume.

**`.claude/agents/set-builder.md`**
- Purpose: build a full DJ set from a vibe description + duration.
- Tools: `search_song`, `download_song`, `analyze_track`, `crossfade`, `export_mp3`, plus state tools.
- Uses skills: `harmonic-mixing`, `energy-arc`, `state-management`.
- Checkpoints per track and per transition — a 15-track set doesn't restart from zero on a crash.

**`.claude/agents/track-scout.md`**
- Purpose: search + download N candidate tracks matching a vibe, with analysis metadata.
- Tools: `search_song`, `download_song`, `analyze_track`, plus state tools.
- Uses skills: `harmonic-mixing`, `state-management`.

### Skills

- **`mashup-recipe`** — step-by-step procedure for a clean mashup (isolate vocal, key-shift to match, align downbeats, level match).
- **`beat-snapping`** — rules for snapping edits to the nearest beat/downbeat/bar.
- **`harmonic-mixing`** — Camelot wheel rules, tempo drift tolerance, energy transitions.
- **`energy-arc`** — how to structure a DJ set's energy curve (intro, build, peak, breakdown, outro).
- **`state-management`** ⭐ — how every subagent must checkpoint work:
  - First step of any job: `state_get(job_id)` to see what's already done.
  - After every meaningful step: `state_update(job_id, step=..., status="done", artifacts={...})`.
  - On start-up, orchestrator runs `state_list_open()` and asks the user whether to resume or start fresh.
  - Step names are stable strings (`search`, `download_a`, `download_b`, `analyze_a`, `analyze_b`, `mashup`, `export`) so resume is deterministic.
  - Artifacts (track IDs, file paths, analysis JSON) are persisted so the next step can find them without re-running.

---

## 8. Web UI (control surface for finished remixes)

**Scope:** the web UI is purely a **post-remix control surface**. It works over `storage/processed/` — the library of tracks that have already been remixed, mashed up, or built into sets by Claude Code. It does not initiate generation. Generation (search, download, mashup, set-build) always goes through Claude Code / MCP.

Single-page vanilla JS app served from FastAPI at `/`. Sections:

- **Processed library** — table of finished outputs from `storage/processed/` with BPM/key/duration and the agent job they came from. Click to load into the deck.
- **Deck** — wavesurfer.js waveform, play/pause/scrub, mark cue points (persisted per track).
- **Live FX preview** — knobs for reverb wet, filter cutoff, delay wet, EQ bands. Applied **non-destructively** in the browser (Web Audio API) for real-time preview; "Commit" button sends the current settings to the server which renders a new file in `storage/processed/`.
- **Export panel** — export current deck to MP3 or short IG/TikTok clip via `/api/export/*`.
- **Job history** — list of past agent jobs from `state.db` with status and link to their output.

WebSocket message shape:
```json
{ "type": "fx_preview", "tool": "filter", "params": { "cutoff": 800 } }
{ "type": "fx_commit", "track_id": "...", "chain": [ {"tool":"filter","params":{}}, ... ] }
{ "type": "job_progress", "job_id": "...", "percent": 42, "message": "Rendering commit" }
```

**Not in the web UI**: search, download, mashup, set-builder. Those are Claude Code territory. The web UI is where you polish the output.

---

## 9. Build phases — copy-paste prompts for Claude Code

Each phase is one Claude Code session ending in one commit. Prompts are ready to paste.

### Phase 0 — Scaffold (30 min)

> Initialize a Python project `dj-mcp` using `uv` and `pyproject.toml`. Python 3.11+. Create the folder structure in `PLAN.md` section 4. Add deps (all MIT/BSD/ISC — no GPL): `fastapi`, `uvicorn[standard]`, `mcp`, `yt-dlp`, `duckduckgo-search`, `pydub`, `librosa`, `soundfile`, `numpy`, `scipy`, `demucs`, `sqlmodel`, `websockets`, `pytest`. Explicitly do NOT add `pedalboard` — effects are hand-rolled on `scipy.signal`. Create `djmcp/server.py` with a FastAPI app exposing `GET /health` returning `{"status": "ok", "version": "0.1.0"}`. Add a `python -m djmcp` entry point in `djmcp/__main__.py` that runs `uvicorn djmcp.server:app --port 8000 --reload`. Add a `LICENSE` file (MIT). Verify with `curl localhost:8000/health`. Commit as `phase-0: scaffold`.

**Checkpoint:** `curl localhost:8000/health` → 200.

### Phase 1 — YouTube tools (1-2 hrs)

> In `djmcp/tools/youtube.py`:
> - `search_song(query: str, limit: int = 5) -> list[dict]`. First try yt-dlp `ytsearch{limit}:{query}` (mimics a real user search). If the result is unusable — 0 items, all items >30 min (mixes/albums), or all uploader/titles clearly unrelated to the query terms — fall back to `web_search.find_youtube(query, limit)`. Return `[{title, url, duration, uploader, thumbnail, source: "yt"|"web"}]`.
> - `download_song(url: str, out_dir: Path | None = None) -> dict` downloads bestaudio, converts to mp3 320kbps via ffmpeg postprocessor, saves to `storage/tracks/`. Return `{track_id, path, title, duration}`. `track_id` is a slug of title + short hash.
>
> In `djmcp/tools/web_search.py`:
> - `find_youtube(query: str, limit: int = 5) -> list[dict]` using `duckduckgo-search` for `"{query} site:youtube.com"`. Filter to `youtube.com/watch?v=` URLs. For each URL, run `yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}).extract_info(url, download=False)` to get real metadata. Return same shape as `search_song` but with `source: "web"`. Skip any URL where extract_info fails or duration > 30 min.
>
> Expose both under `POST /api/youtube/search` and `POST /api/youtube/download` in a new router `djmcp/routes/youtube.py`, mounted in `server.py`. `download` should return a `job_id` and run in the background using FastAPI `BackgroundTasks` if duration > 10 min.
>
> Add `djmcp/jobs.py` with a simple in-process async job registry: `create_job()`, `update_progress(job_id, percent, message)`, `get_job(job_id)`.
>
> Tests in `tests/test_youtube.py`: (a) `test_search_yt_hit` uses a common query that yt-dlp handles; (b) `test_search_web_fallback` uses a deliberately obscure/mangled query and monkeypatches yt-dlp search to return `[]`, asserts that the web fallback returns real results with `source == "web"`. Mark network tests with `@pytest.mark.integration`. Commit as `phase-1: youtube search + web fallback + download`.

**Checkpoint:** Normal query returns yt-dlp results (`source: "yt"`). Obscure/mangled query with monkeypatched empty yt-dlp still returns results via web fallback (`source: "web"`). Download produces a playable mp3 in `storage/tracks/`.

### Phase 2 — Analysis + basic editing (2 hrs)

> In `djmcp/tools/analysis.py` implement `analyze_track(track_id) -> dict` using librosa: BPM (via `librosa.beat.beat_track`), key (chroma_cqt + Krumhansl-Schmuckler profile matching), Camelot notation, duration, beat times, section boundaries (`librosa.segment.agglomerative` on MFCCs), and mean energy per section. Cache result as `storage/tracks/{track_id}.json` sidecar; return cached on subsequent calls.
>
> In `djmcp/tools/edit.py`:
> - `trim(track_id, start_sec, end_sec, snap_to_beat=True)` — if snap, move start/end to nearest beat time from cached analysis. Save to `storage/processed/`.
> - `split_at_beats(track_id, beat_indices: list[int])` — return list of new track_ids.
> - `extract_section(track_id, section_name)` — use analyzed sections; support `"intro"`, `"drop"`, `"breakdown"`, `"outro"` by heuristics on energy + position.
>
> Expose under `POST /api/analysis/analyze` and `POST /api/edit/*`. Tests with a bundled 30-sec CC0 test file at `tests/fixtures/test.mp3`. Commit as `phase-2: analysis + edit`.

**Checkpoint:** `analyze_track` returns sensible BPM (±2) for a known track. `trim` with snap produces cuts on beat boundaries.

### Phase 3 — Effects and boosters (1-2 hrs)

> In `djmcp/tools/effects.py` implement using `scipy.signal` + `numpy` only (no pedalboard):
> - `apply_reverb(track_id, room_size=0.5, wet=0.3)` — Schroeder reverb: 4 parallel comb filters (delays ~29/37/41/43 ms scaled by room_size, feedback ~0.84) into 2 series all-pass filters (~5/1.7 ms). Dry/wet mix. Implement combs and all-passes with `scipy.signal.lfilter` and hand-built delay lines on numpy arrays.
> - `apply_filter(track_id, type: "lowpass"|"highpass"|"bandpass", cutoff_hz, resonance=0.7)` — biquad IIR from `scipy.signal.iirfilter(2, cutoff, btype=..., ftype="butter", output="sos")` then `sosfilt`. Map resonance to Q.
> - `apply_delay(track_id, time_ms=250, feedback=0.3, wet=0.3)` — delay line (numpy circular buffer) with feedback, dry/wet mix. No library needed beyond numpy.
> - `apply_eq(track_id, low_gain=0, mid_gain=0, high_gain=0)` — 3-band shelving EQ. Hand-write low-shelf, peaking mid, high-shelf biquad coefficients (RBJ audio EQ cookbook formulas), apply with `sosfilt`.
>
> In `djmcp/tools/boosters.py`:
> - `bass_boost(track_id, gain_db=6)` — low-shelf via `apply_eq(low_gain=gain_db)` below 200 Hz.
> - `vocal_boost(track_id, gain_db=6)` — demucs split → gain vocal stem → remix (async, returns job_id).
> - `energy_lift(track_id, amount=0.5)` — hand-rolled compressor (envelope follower with attack/release, threshold, ratio, makeup gain) + high-shelf + light soft-clip saturation (tanh). All numpy.
>
> All functions save to `storage/processed/` and return `{track_id, path}`. Prevent clipping (peak-normalize at -1 dBFS). Expose under `/api/fx/*` and `/api/boost/*`. Tests A/B compare RMS energy pre/post. Commit as `phase-3: effects + boosters (scipy)`.

**Checkpoint:** Before/after `bass_boost(gain=6)` is audibly different, no clipping.

### Phase 4 — Mix tools (2-3 hrs)

> In `djmcp/tools/mix.py`:
> - `crossfade(track_a_id, track_b_id, bars=8)` — beat-match track_b to track_a's BPM using `librosa.effects.time_stretch` if drift < 10%, align first downbeats, linear cross-EQ over N bars.
> - `overlay_loop(track_id, loop_name, bars, start_beat=0)` — bundle 15 CC0 drum/808 loops in `storage/loops/` (document sources in `storage/loops/README.md`). Loop is beat-aligned to track's BPM.
> - `mashup(vocal_track_id, instrumental_track_id)` — demucs split vocal_track, extract vocal stem, key-shift to match instrumental key (semitone shift via librosa pitch_shift, up to ±3), align first downbeat, level-match to -6 dBFS on vocal, mix.
>
> Long-running (`mashup`, `overlay_loop` with heavy processing) return `job_id`. Expose under `/api/mix/*`. Tests: crossfade of two same-key tracks produces smooth transition (measure RMS discontinuity at seam). Commit as `phase-4: mix`.

**Checkpoint:** Crossfade between two tracks in the same key sounds smooth. Mashup produces an aligned vocal-over-instrumental mix.

### Phase 5 — Export tools (30 min)

> In `djmcp/tools/export.py`:
> - `export_mp3(track_id, bitrate=320)` — copy to `storage/exports/`, return path.
> - `short_clip(track_id, duration=30, format="ig")` — auto-center on the highest-energy section (analyze if not cached), fade in/out 500ms, format-specific specs (IG: 1080x1080 waveform video optional, but MP3 is fine for v1; TikTok/Shorts: 60s max).
>
> Expose under `/api/export/*`. Commit as `phase-5: export`.

**Checkpoint:** `short_clip` produces a 30-sec MP3 with the drop centered.

### Phase 5.5 — State management (1-2 hrs) ⭐

> In `djmcp/tools/state.py` implement a SQLite-backed job store at `storage/state.db` using `sqlmodel`. Schema:
> - `Job`: `id` (uuid), `agent` (str), `goal` (str, the user's original request), `status` ("open"|"done"|"failed"), `created_at`, `updated_at`.
> - `JobStep`: `id`, `job_id` (FK), `step` (str, e.g. "search", "download_a", "analyze_a", "mashup", "export"), `status` ("pending"|"done"|"failed"), `artifacts` (JSON — track_ids, paths, params), `updated_at`.
>
> Functions:
> - `state_create_job(agent, goal, params) -> job_id`
> - `state_update(job_id, step, status, artifacts=None)` — upsert a JobStep, bump Job.updated_at, set Job.status="failed" if a step fails.
> - `state_get(job_id) -> dict` — full job + all steps, plus a computed `next_step` (first pending/missing step in the agent's known sequence).
> - `state_list_open(agent=None) -> list[dict]` — jobs with status "open", optionally filtered by agent, newest first.
> - `state_resume(job_id) -> dict` — same as state_get but also sets a `resumed_at` marker for logging.
>
> Expose all five under `/api/state/*` (see PLAN.md section 5) and as MCP tools (`mcp__djmcp__state_*`). Tests: create a job, update 3 steps, kill and re-fetch, assert `next_step` is correct; simulate a failed step and assert `state_list_open` still surfaces it for resume. Commit as `phase-5.5: state management`.

**Checkpoint:** Create a job, update two of four steps, call `state_get` — `next_step` correctly points to the third step. Restarting the process and calling `state_list_open` still shows the job.

### Phase 6 — MCP adapter (1-2 hrs) ⭐

> In `djmcp/mcp_adapter.py` create an MCP server using the official `mcp` Python SDK that exposes every function in `djmcp/tools/*` (including `state.py`) as an MCP tool with proper JSON schemas derived from the function signatures. Long-running ops return `{job_id}` immediately and stream progress via MCP notifications (`notifications/progress`).
>
> Add `python -m djmcp.mcp` entry (in `djmcp/mcp_adapter/__main__.py`) that runs the MCP server on stdio.
>
> Document in README the Claude Code config snippet:
> ```json
> {
>   "mcpServers": {
>     "djmcp": {
>       "command": "python",
>       "args": ["-m", "djmcp.mcp"],
>       "cwd": "/absolute/path/to/dj-mcp"
>     }
>   }
> }
> ```
> And the equivalent GHCP config.
>
> Commit as `phase-6: mcp adapter`.

**Checkpoint:** Add MCP to Claude Code config, ask *"search for Daft Punk One More Time and download it"* — it runs end-to-end. Also test with a deliberately garbled song description to confirm the web-search fallback path fires.

### Phase 7 — Orchestrator, subagents + skills (2-3 hrs)

> Create `.claude/agents/` and `.claude/skills/` at repo root.
>
> Subagents (each is a `.md` file with YAML frontmatter: `name`, `description`, `tools`, `model: sonnet`):
>
> - **`dj-orchestrator.md`** ⭐ — the single entry point. On any user request: (1) call `state_list_open` — if there's an open job matching the request's intent, ask the user "resume job X (last step: Y) or start fresh?"; (2) otherwise call `state_create_job(agent, goal, params)`; (3) delegate to the matching specialist subagent via `Task`, passing the `job_id`; (4) on the specialist's completion or failure, report back to the user with the state summary. Restricted tools: `mcp__djmcp__state_create_job`, `state_get`, `state_list_open`, `state_resume`, `Task`. Never calls audio tools directly.
> - **`mashup-builder.md`** — receives a `job_id` from the orchestrator (or creates its own if run standalone). Steps, each checkpointed via `state_update(job_id, step=...)`: `search` (both tracks; use web-search fallback transparently if yt-dlp search fails) → `download_a`/`download_b` → `analyze_a`/`analyze_b` → compatibility check (harmonic-mixing skill) → `mashup` → `export`. Before starting, call `state_get(job_id)` and skip any step already marked "done". Restricted tools: `mcp__djmcp__search_song`, `download_song`, `analyze_track`, `mashup`, `export_mp3`, `state_update`, `state_get`.
> - **`set-builder.md`** — input: vibe + duration + `job_id`. Checkpoints per track and per transition (`track_1`, `track_2`, ..., `transition_1_2`, ...) so a 15-track set resumes mid-build rather than restarting. Restricted tools: `search_song`, `download_song`, `analyze_track`, `crossfade`, `export_mp3`, `state_update`, `state_get`.
> - **`track-scout.md`** — searches and downloads N candidate tracks matching a vibe, checkpoints per candidate, returns table with BPM/key/energy. Restricted tools: `search_song`, `download_song`, `analyze_track`, `state_update`, `state_get`.
>
> Skills (each folder with `SKILL.md`):
> - `mashup-recipe/` — procedure: isolate vocal from track A, isolate instrumental from track B, key-check, key-shift vocal ±3 semitones if needed, align downbeats, level-match, mix.
> - `beat-snapping/` — snap start/end to nearest beat by default, downbeat if user says "bar", never off-grid unless user overrides.
> - `harmonic-mixing/` — Camelot wheel rules: same key, ±1, relative maj/min, +7 semitones for energy boost. Tempo drift ±6% smooth, ±10% cut.
> - `energy-arc/` — set structure: intro (low energy, 10%), build (rising, 30%), peak (high, 30%), breakdown (drop, 15%), outro (fade, 15%).
> - `state-management/` ⭐ — the contract every subagent follows: check `state_get` before starting, use stable step-name strings per agent type (document the exact step-name sequence for each of the three specialist agents), update state after every meaningful step with enough `artifacts` (track_ids, file paths, analysis JSON) that a later step never has to redo work, mark the job "failed" with a clear reason if a step errors rather than silently stopping.
>
> Update README with the "quickstart" for a user: clone, install, run server, copy `.claude/` into their project, add MCP config, ask `/agents mashup-builder ...`. Commit as `phase-7: subagents + skills`.

**Checkpoint:** Fresh Claude Code session, run `mashup-builder` with two song descriptions, get a mashup file back.

### Phase 8 — Real-time web UI (3-4 hrs)

> Build `web/index.html` + `web/app.js` + `web/style.css`. Vanilla JS + wavesurfer.js from CDN. This UI works **only on already-processed tracks** in `storage/processed/` — it has no search/download/mashup buttons; those stay in Claude Code. Sections:
> - **Processed library**: table of `storage/processed/` outputs (from `GET /api/library/processed`) with BPM/key/duration and which agent job produced them (join against `state.db`). Click to load into deck.
> - **Deck**: waveform display (wavesurfer.js), play/pause/scrub, mark cue points, persisted per track_id in a small `cues.json` sidecar.
> - **Live FX preview**: knobs for reverb wet, filter cutoff, delay wet, EQ bands. Value change sends `{type: "fx_preview", tool, params}` over WS; apply via Web Audio API `BiquadFilterNode`/`ConvolverNode` client-side for zero-latency preview — do not round-trip to the server for preview. A "Commit" button sends `{type: "fx_commit", track_id, chain}`; server re-renders using the same `djmcp/tools/effects.py` functions and saves a new file in `storage/processed/`.
> - **Export panel**: buttons for MP3 export and short-clip (IG/TikTok/Shorts) export via `/api/export/*`.
> - **Job history**: read-only list from `GET /api/state/jobs?open=false` showing completed agent jobs and linking to their output file.
>
> Mount static files in `server.py`: `app.mount("/", StaticFiles(directory="web", html=True))`. Add `WS /ws` handler in `djmcp/ws.py` for fx_preview/fx_commit/job_progress messages. Commit as `phase-8: web ui (post-remix control surface)`.

**Checkpoint:** Open `localhost:8000`, see a track that Claude Code already remixed via `mashup-builder` listed in the processed library, load it, turn the filter knob and hear the live preview, hit Commit and see a new file appear in `storage/processed/`.

### Phase 9 — Landing page + distribution (2 hrs)

> Create `site/` folder with a static landing page (separate from the app UI):
> - Hero: "Turn Claude Code into your DJ assistant"
> - 30-sec demo video placeholder
> - One-click install config snippets for Claude Code / GHCP / Cursor (copy-to-clipboard buttons)
> - "What it does" — 4 example prompts with expected output
> - Email capture (Formspree or Buttondown embed)
> - GitHub Sponsors button
> - Affiliate strip: Splice, Loopcloud, Rekordbox (placeholder links)
> - Footer: GitHub, docs, Discord
>
> Deploy via GitHub Pages from `site/`. Update README with `djmcp.io` link (or `<username>.github.io/dj-mcp`). Commit as `phase-9: landing`.

**Checkpoint:** Landing page live, copy-paste config works in Claude Code.

---

## 10. Testing strategy

- **Unit tests** — each tool function, mock external I/O where possible.
- **Integration tests** — marked `@pytest.mark.integration`, hit real YouTube (short CC-BY video), run real analysis.
- **Golden files** — bundle 3-5 short CC0 audio fixtures in `tests/fixtures/`; assert BPM, key, section counts within tolerance.
- **Manual smoke** — end of each phase, run the checkpoint prompt from Claude Code.

CI: GitHub Actions, run unit tests on push; integration tests nightly.

---

## 11. Legal + safety notes

- **YouTube downloads**: personal/local use only. Do not host as a public service. README states this.
- **Copyright**: outputs of remixes/mashups from copyrighted material are not for Spotify distribution. See `docs/legal.md` (to be written) for what's OK where (SoundCloud tolerates, Mixcloud is licensed, Spotify needs original or licensed material).
- **Bundled loops** in `storage/loops/`: must be CC0 or explicit permissive license. Document each loop's source in `storage/loops/README.md`.
- **User data**: nothing leaves the machine. No telemetry in v1.

---

## 12. Monetization roadmap (post-v1)

Free forever: MCP server, REST API, web UI, subagents, skills — all MIT, all on GitHub.

Paid layers, added on top later:

1. **Hosted tier at `djmcp.io`** — GPU-accelerated stem separation, faster mashups. $9-19/mo.
2. **Pro Pack extension** — advanced tools (Rekordbox export, auto-mashup, stem-based remixing with better models). One-time $29 or $5/mo.
3. **Landing page revenue** — affiliate links (Splice, Loopcloud), email list, GitHub Sponsors.
4. **Sponsored loop/sample packs** — bundled with attribution, upsell paid packs.

No ads. Email capture from day 1.

---

## 13. Launch checklist

- [ ] All 9 phases green
- [ ] README with quickstart, config snippets, screenshots
- [ ] 60-second demo video (screen recording of Claude Code building a mashup + web UI)
- [ ] Landing page live
- [ ] Post to: r/DJs, r/LocalLLaMA, r/MachineLearning, Hacker News, X, LinkedIn (Agent Factory angle)
- [ ] Submit to the Anthropic MCP directory
- [ ] Discord server for user support

---

## 14. Success signals (first 90 days)

| Metric | 30 days | 60 days | 90 days |
|---|---|---|---|
| GitHub stars | 100 | 500 | 1500 |
| Email subs | 50 | 250 | 750 |
| Discord members | 20 | 100 | 300 |
| Landing page visitors | 500 | 2500 | 8000 |
| One viral moment (DJ influencer shares a mashup) | — | maybe | yes |

If two of these hit by day 60, add the hosted tier. If none hit by day 60, pivot: reposition as "AI music production assistant" for producers rather than DJs.
