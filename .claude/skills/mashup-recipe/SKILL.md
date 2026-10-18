---
name: mashup-recipe
description: Step-by-step procedure for building sequence, layered or combined mashups from analyzed tracks, including choosing the style, ranking combinations, running slow jobs and checking the result. Use in mashup-builder.
---

# Mashup recipe

Inputs: `job_id` and a set of tracks, usually from track-scout's `candidate_N` steps (read them with `state_get`). If you were given song names and no tracks, fetch them yourself with `search_song`, `download_song`, `analyze_track` and checkpoint `download_N` / `analyze_N`.

## 1. Choose the style

If the user's words already say it ("blend them one after another", "put the vocals of A over B") use that. Otherwise ask with `request_input` (see ask-policy), key `style`:

- "One after another" (sequence)
- "Vocals over another song's beat" (layered)
- "A bit of both" (both)

Defaults: 2 songs, layered. 3 to 4 songs, both. 5 or more, sequence. Layered needs at least 2 songs.

## 2. Plan the combinations (`plan`)

1. Call `plan_mixes(track_ids, mode, top_k=4, titles={track_id: title})`.
2. Pick the plan:
   - If the job is long (more than 4 songs) or the top two scores are within 0.1, ask with `request_input` key `plan_choice`. Options are the plans' summaries with a short reason, default the top plan.
   - Otherwise take the top plan and record `state_add_assumption("Chose <summary> because <reason>")`.
3. Save it: `state_set_plan(job_id, <the chosen plan>)` and checkpoint `plan`.
4. On a resume, if `job.plan` already exists, use it. Do not re-plan.

## 3. Build (`mix_1` … `mix_M`)

Work through the plan's steps in order.

**Layered step** (`type: "layered"`):
1. `transcribe_track(vocal, language=<hint if known>)`. This takes a while; it is cached.
2. Pick the vocal window. Use `analyze_track(vocal)` sections: take the highest-energy middle section, or the first full verse-and-hook, 20 to 45 seconds. See smooth-transitions.
3. `mashup(vocal, instrumental, vocal_start_sec, vocal_end_sec)` returns a `job_id`. Then loop `wait_for_job(job_id, 60)` until its status is `done` or `failed`. It takes minutes; that is normal. Do not start the call twice.
4. Record `mix_N` with the result `track_id`, `path` and `kind: "layered"`. Note the `vocal_entry_sec` and `key_shift_semitones` it reports.

**Sequence** (consecutive `track` steps): `medley(track_ids_in_order, bars=<the plan's transition_bars, usually 8>)`. For a plan that starts with a layered step, the layered result `track_id` is the first track in the list. Record `mix_N` with `kind: "medley"`.

If a step fails, checkpoint it as failed with a plain-language reason and stop.

## 4. Smooth check and export

Follow smooth-transitions: `check_seams`, one repair attempt, checkpoint `smooth_check`. Then `export_mp3(track_id)` and checkpoint `export` with `{track_id, path}`.

## 5. Report

Final message:

```
STATUS: done
TRACK_ID: <final track_id>
PATH: <path>
SUMMARY: <one or two plain sentences: what was combined and any compromise, such as a key shift or a short transition>
```
