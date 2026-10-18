---
name: beat-snapping
description: Rules for placing cuts, loops and edits on the beat or bar grid. Use whenever trimming, splitting or overlaying loops.
---

# Beat snapping

- **Default: snap to the nearest beat.** `trim` does this when `snap_to_beat` is true (the default). Leave it on.
- **Bars:** if the user talks about bars, phrases or "clean" cuts, snap to a downbeat and use multiples of 4 bars (8 for phrases). Choose `start_sec` and `end_sec` from the track's `beat_times`, every fourth beat from the first.
- **Loops:** `overlay_loop` takes `start_beat`, an index into the beat grid. Use a multiple of 4 so the loop starts on a bar, and a `bars` value of 2, 4 or 8.
- **Never go off-grid** unless the user explicitly asks for a specific second.
- **Splitting:** `split_at_beats` takes beat indices; pick multiples of 16 (4 bars) for natural sections.
