# DJ MCP: Agents Plan (Phase 7), v2

> **Status: built.** Differences from the plan below, as implemented:
> - The UI polls the job record every 1.5 s instead of using WebSockets, and draws the deck waveform itself from server-computed peaks (no CDN dependency).
> - Extra tools beyond the plan: `plan_mixes` (deterministic ranking of combinations), `wait_for_job` (agents cannot sleep), `list_loops`, `open_ui`, `state_set_plan`, `state_add_assumption`, `state_complete`.
> - Agents launch the UI dynamically: in a Claude Code chat the orchestrator calls `open_ui`, which starts the server if needed and opens the browser (or jumps an open tab to the job).
> - Choosing "continue the old job" from the UI closes the new job with a pointer and the runner restarts the old one.
> - `mashup` now only key-shifts when the shift is within 3 semitones (a clamped partial shift left the vocal off-key).
> - Not verified: the real `claude -p --agent` run. The runner is tested against a stand-in executable.

## 1. What changed from v1

| Your input | How the plan changes |
| --- | --- |
| Orchestrator must ask whether to continue an old job | Hard rule, shown as a "Continue or start new?" card in the UI (section 3). |
| Track-scout needs a planner for vague requests | New `remix-planner` skill plus a `find_trending` tool, so "trending Bollywood songs" works with no further detail (section 5). |
| Mashup-builder asks: sequence, layered, or both; lists combinations; can plan alone | Three modes, a ranked list of combination plans, and an Autopilot switch that picks the best plan without asking (section 6). |
| Transitions smooth; words never start abruptly | A `smooth-transitions` skill with measurable rules and a check step. It needs some engine work in `mix.py` (section 6). |
| A UI for non-technical users instead of chat | The UI becomes the front door and runs the agents. This reverses the original Phase 8 scope (section 4). |

## 2. Design principle: decide, don't interrogate

A request like **"create a mashup with the trending songs in Bollywood"** must produce a finished mashup with nothing else typed. Agents follow one rule: *if something is unclear, make a sensible choice, record it as an assumption, and keep going.* They ask only when the answer changes the result a lot, and every question has a default so the user can just press Continue. An **Autopilot** switch turns all questions off.

Questions are limited to three kinds:

1. Continue an old job or start new (always asked if a matching open job exists, unless Autopilot is on, which continues the most recent match).
2. Mashup style, only if the user did not say (sequence, layered or both).
3. Approve the plan, only for long jobs (more than 4 songs, or an estimated runtime over 15 minutes).

## 3. User experience (UI-first)

1. **Home.** One text box, example chips ("Trending Bollywood mashup", "Chill 30-minute set"), an Autopilot toggle, and a "Resume" list of unfinished jobs.
2. **Continue or start new?** Shown when an open job matches. It lists the job, its last finished step and its age, with buttons "Continue" and "Start new".
3. **Questions.** At most one short form with defaults pre-selected, such as "Style: Sequence / Layered / Both" and a list of plan options.
4. **Progress.** Step list (Finding songs, Downloading, Analyzing, Planning, Mixing, Smoothing, Exporting) with live status and a time estimate. Mixing uses stem separation, which is slow on CPU.
5. **Result.** Player with waveform, download button, the list of assumptions the agents made, and a "Make a variation" button. The post-production deck (Phase 8b) opens from here.

## 4. Architecture change: the UI runs the agents

The original plan said the UI never starts generation and the server never calls an LLM. Both change. The server gains a thin **runner** that launches Claude Code in the background, and everything else stays a plain tool executor.

- **Runner.** `POST /api/requests {text, autopilot}` creates a state job and starts `claude -p --agent dj-orchestrator --output-format stream-json` with only the `mcp__djmcp__*` tools allowed. Output is streamed to the UI over WebSocket as progress events.
- **Questions from agents.** A new MCP tool `request_input(job_id, kind, prompt, options, default)` stores the question in the state database and sets the job to `waiting_input`. The agent ends its turn. The UI shows the form, `POST /api/state/jobs/{id}/answer` saves the reply, and the runner restarts the orchestrator on that job. This reuses the resume design already built, and it avoids a blocking tool call that could time out.
- **State.** Add the status `waiting_input` plus `plan` and `assumptions` fields to the job record.
- **Requirements the user must have.** Claude Code installed and signed in on the same machine, because every request uses their Claude usage. The first-run screen should check this and explain it in plain words.
- **Safety.** Headless runs cannot approve permission prompts, so the allow-list must be exact: djmcp tools only, no shell, no file writes.

## 5. Agents

| Agent | Job | MCP tools | Checkpoint steps |
| --- | --- | --- | --- |
| dj-orchestrator (main agent) | Reads the request, runs the continue-or-new check, opens or resumes the job, delegates, returns the result and the assumptions list | `state_*`, `request_input`, `get_job`, spawn subagents. No audio tools | `intake`, `resume_check`, `delegate`, `report` |
| track-scout | Turns any request, even vague, into a list of real tracks (see below) | `find_trending`, `search_song`, `download_song`, `analyze_track`, `state_*` | `interpret`, `research`, `shortlist`, `candidate_1` … `candidate_N` |
| mashup-builder | Plans combinations, builds sequence and layered mashups, checks smoothness | scout tools, `transcribe_track`, `extract_section`, `crossfade`, `mashup`, `get_job`, `request_input`, `export_mp3` | `plan`, `approve` (if asked), `download_1…N`, `analyze_1…N`, `mix_1…M`, `smooth_check`, `export` |
| set-builder | Full DJ set from a vibe and duration | scout tools, `extract_section`, `crossfade`, `export_mp3` | `track_1…N`, `transition_1_2…`, `export` |
| finisher | EQ, bass boost, loop overlay, short clip on a finished output | `apply_*`, `bass_boost`, `energy_lift`, `overlay_loop`, `short_clip`, `export_mp3` | `fx_1…N`, `export` |

Because the number of songs now varies, `mashup-builder` needs dynamic step names like `set-builder`. The fixed `AGENT_STEPS` entry in `state.py` is removed for it.

### Track-scout and the `remix-planner` skill

For a vague request the scout works in four stages:

1. **Interpret.** Pull out region, genre or language, mood, era, count and what is missing. Defaults: 4 songs, current year, upbeat.
2. **Research.** Call `find_trending(region, genre, limit)`, a new tool built on the existing Firecrawl search, which reads current charts. If charts fail, fall back to `search_song` on queries like "top Bollywood songs this month".
3. **Shortlist.** Search and analyze about twice as many songs as needed. Drop anything over 30 minutes, any live or remix upload, and any song with a bad BPM or key detection.
4. **Hand over.** Give `mashup-builder` the shortlist with BPM, key, energy and a vocal-heavy or instrumental-heavy flag, plus the assumptions it made ("Interpreted 'trending' as the top 6 on current Indian charts").

## 6. Mashup-builder in detail

### Modes

| Mode | What it makes |
| --- | --- |
| Sequence (medley) | Song A flows into B into C, with a transition between each pair. |
| Layered | The vocal of one song over the instrumental of another (existing `mashup` tool). |
| Both | A sequence in which some segments are layered. |

If the user did not say, it asks once with "Both" or "Sequence" pre-selected, depending on the song count.

### Combination planner

1. For every pair in the shortlist, score: Camelot key distance, tempo gap (percent), energy fit, and vocal/instrumental balance.
2. Build candidate plans, for example "A → C → B in sequence" or "vocal of A over instrumental of D, then into B".
3. Rank them and show the top 3–5 as readable cards with a one-line reason each ("A and C share a key, 4% tempo gap").
4. Normal mode: the user picks. Autopilot: it takes the top plan and records why.
5. The chosen plan is saved in the job's `plan` field, so a resume does not re-plan.

### `smooth-transitions` rules

- Cut and enter only on bar boundaries, ideally phrase boundaries (multiples of 8 bars).
- Sequence transitions: crossfade over 4–8 bars, gradual tempo ramp when the gap is over 3%, swap the bass between the two songs instead of overlapping it.
- Songs more than 10% apart in tempo, or with clashing keys: use a cut at a phrase end with a short effect (reverb tail or filter sweep), not a long blend.
- **Vocals never start abruptly.**
  - Use the lyric timestamps from `transcribe_track`. A vocal segment starts at the beginning of a line, with about one bar of lead-in, and ends at the end of a line. It never cuts mid-word.
  - Fade the vocal in over about one bar and out over about one bar.
  - Where two vocals meet in a sequence, one must finish before the other starts, or both must be gated.
- **Smooth check step.** After mixing, measure level jumps at each seam, as the existing crossfade test does. If any seam fails, adjust (longer fade, different cut point) and re-check once before exporting.

### Engine work this needs (not built yet)

I have not reviewed these against `mix.py` in detail, so treat the list as a starting point:

- Vocal fade-in and fade-out, and a start-at-line-boundary option in `mashup`.
- A `medley` tool that chains `crossfade` over many tracks with the transition rules above.
- A `check_seams` tool that returns a pass or fail per seam.
- `find_trending`, `request_input`, and the new state fields.

## 7. Skills

| Skill | Contents | Used by |
| --- | --- | --- |
| state-management | Call `state_get` first, skip finished steps, checkpoint after every step, mark failures clearly, never retry silently | all |
| ask-policy (new) | The three allowed question kinds, always attach a default, Autopilot means no questions, record every assumption | orchestrator, scout, mashup-builder |
| remix-planner (new) | The four scout stages, default values, how to read charts, shortlist filters | track-scout |
| smooth-transitions (new) | The rules and the seam check above | mashup-builder, set-builder |
| harmonic-mixing | Camelot rules, tempo drift limits, key shift of at most ±3 semitones | scout, mashup-builder, set-builder |
| mashup-recipe | Modes, combination scoring, order of work, polling `get_job` while stems separate | mashup-builder |
| energy-arc | Set shape: intro 10%, build 30%, peak 30%, breakdown 15%, outro 15% | set-builder |
| beat-snapping | Snap to beats by default, to downbeats on request | finisher, set-builder |

## 8. Build order

| Stage | Work | Rough time |
| --- | --- | --- |
| 7a | Engine: `find_trending`, `request_input`, state fields, vocal fades and line-boundary start, `medley`, `check_seams`, with tests | 3–4 h |
| 7b | The eight skills and five agents; first end-to-end run of "trending Bollywood mashup" from the command line | 2–3 h |
| 8a | Request UI and runner: home, questions, progress, result, resume list | 4–5 h |
| 8b | Post-production deck (waveform, live effects preview, export) as in the original plan | 3–4 h |

Test order: (1) a one-line vague request in Autopilot, (2) the same with questions on, (3) kill a run mid-mix and resume it from the UI, (4) listen to every seam and the first second of every vocal entry.

## 9. Risks

- **Runtime.** Stem separation on CPU can take minutes per song. A 5-song mashup may take well over 15 minutes, so the UI needs honest progress and an estimate.
- **Trend sources.** Chart pages change or block scraping. The fallback search keeps it working but with less accurate "trending".
- **Quality.** Auto-planned mashups will sometimes sound wrong. The "Make a variation" button and the plan cards are the safety net.
- **Rights.** Trending songs are copyrighted. The existing personal-use note stays in the README and the UI footer.
- **Claude Code dependency.** Non-technical users must install and sign in to Claude Code once. This is the biggest barrier to the "non-tech friendly" goal, and it needs a clear first-run screen.

## 10. Open questions

- [ ] Should Autopilot be on by default?
- [ ] Is the plan-approval threshold right (more than 4 songs or over 15 minutes)?
- [ ] Is requiring Claude Code on the user's machine acceptable for the first version?
- [ ] Which regions and languages should `find_trending` support first (Bollywood only, or more)?
- [ ] Do you want Phase 8a (request UI) built before 7b, so the first test is through the UI instead of the command line?
