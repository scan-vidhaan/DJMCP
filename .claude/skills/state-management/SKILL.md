---
name: state-management
description: How every DJ agent checkpoints work so a stopped or interrupted job resumes without redoing anything. Use at the start of any djmcp job and after every meaningful step.
---

# State management

Every job has a `job_id`. All progress lives in the djmcp state store, never in your memory, because a run can stop at any point (the user closes the app, a question is waiting for an answer, a crash) and a fresh run must pick up exactly where this one left off.

## Rules

1. **Read before you work.** Your first call is `state_get(job_id)`. Steps already `done` are finished: do not redo them. Their `artifacts` hold what you need (track ids, paths, analysis, the chosen plan). `next_step` tells you where to continue.
2. **Checkpoint after every step.** Call `state_update(job_id, step, "done", artifacts={...})` as soon as a step finishes, with enough in `artifacts` that no later step needs to repeat the work: `track_id`, `title`, `path`, BPM and key for songs, the output `track_id` for mixes.
3. **Use the stable step names below.** The web app turns them into friendly progress text, and resuming relies on them.
4. **Fail loudly and plainly.** If a step cannot be completed, call `state_update(job_id, step, "failed", error="...")` with a sentence a non-technical person can read ("I could not find a playable version of 'Song X'"), then stop. Never retry silently in a loop and never skip a step quietly.
5. **Questions park the job.** If `request_input` returns `{"answered": false}`, do nothing else: end your turn. You will be run again after the user answers, and the same `request_input` call will then return the answer.
6. **Record decisions.** When you choose something on the user's behalf, call `state_add_assumption(job_id, "...")` so it is shown on the result page.
7. **Only the orchestrator closes a job** with `state_complete`.

## Step names

| Who | Steps |
| --- | --- |
| dj-orchestrator | `intake`, `resume_check`, `delegate`, `report` |
| track-scout | `interpret`, `research`, `shortlist`, `candidate_1` … `candidate_N` |
| mashup-builder | `plan`, `download_1…N` / `analyze_1…N` (only when it fetches songs itself), `mix_1…M`, `smooth_check`, `export` |
| set-builder | `plan`, `track_1…N`, `transition_1_2` …, `smooth_check`, `export` |
| finisher | `fx_1…N`, `smooth_check`, `export` |

## Artifact conventions

- `candidate_N`: `{track_id, title, bpm, key, camelot, energy, duration}`
- `plan`: `{plan_id, mode, summary}` (the full plan is stored with `state_set_plan`)
- `mix_N`: `{track_id, path, kind}` where kind is `layered` or `medley`
- `smooth_check`: `{passed, jumps}`
- `export`: `{track_id, path}`
