---
name: smooth-transitions
description: Rules for transitions and vocal entries that sound smooth - no abrupt starts, no clipped words, no fighting tempos - plus the seam check and one-retry repair. Use in mashup-builder, set-builder and finisher.
---

# Smooth transitions

A listener should never notice where one song ends and another begins, and a vocal should never start abruptly or get cut mid-word.

## Rules

- **Cut and enter on bar boundaries**, ideally phrase boundaries (multiples of 8 bars). The `medley` and `mashup` tools already work on the beat grid; do not pass arbitrary second offsets that land off-grid.
- **Sequence transitions** (`medley`): 8 bars when two songs are within 10% tempo of each other, which is what `plan_mixes` suggests in `transition_bars`. Beyond 10% the tool automatically uses a short 2-bar blend, because a long blend of two different tempos sounds like two songs fighting.
- **Vocals never start abruptly.** For any layered mashup:
  1. Run `transcribe_track` on the vocal song first, with a `language` hint when you know it (Hindi `hi`, Punjabi `pa`, Tamil `ta`, Telugu `te`, Kannada `kn`). The mashup tool uses those lyric timestamps to start the vocal at the beginning of a line and end it at the end of a line, so no word is clipped.
  2. Pass `vocal_start_sec` and `vocal_end_sec` that cover a complete musical idea (a verse plus hook or a full chorus, 20 to 45 seconds). The tool snaps them outward to line boundaries.
  3. The tool brings the vocal in one bar after the instrumental starts, with a short fade that finishes before the first word. Do not try to defeat this.
- **Two vocals never overlap.** In a plan that mixes layered and sequence parts, the vocal of one segment must have finished before the next begins; the sequence crossfade handles this because the layered result is treated as one track.
- **Ending:** every mix fades out gently. The tools already do this.

## Seam check and repair

After the final mix is built, always run `check_seams(track_id)` and checkpoint `smooth_check` with `{passed, jumps}`.

- If `passed` is true, continue.
- If not, repair **once**:
  - For a medley, rebuild with `bars` increased by 4 (up to 16), or reorder so the jarring pair is not adjacent if the plan has another close option.
  - For a layered mashup, retry with a different vocal window that starts at a different line.
  - Then check again.
- If it still fails, keep the better result, and record an assumption naming the times that may sound abrupt ("A small jump near 2:14 could not be smoothed"). Do not loop further.
