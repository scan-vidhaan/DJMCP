---
name: energy-arc
description: How to shape a DJ set's energy over time (intro, build, peak, breakdown, outro) and order tracks accordingly. Use in set-builder.
---

# Energy arc

A set is not a random playlist; it moves.

| Phase | Share of the set | Energy |
| --- | --- | --- |
| Intro | 10% | Low, sets the mood |
| Build | 30% | Rising |
| Peak | 30% | Highest |
| Breakdown | 15% | Drops, gives a breather |
| Outro | 15% | Fading out |

## Ordering tracks

1. Get each track's `energy` (the `candidate_N` artifacts, or `plan_mixes(...)["tracks"]`).
2. Sort by energy and place them on the arc: lowest at the start, rising through the build, the highest 30% in the peak, one lower track as the breakdown, then the lowest remaining for the outro.
3. Within that frame, adjust neighbours to improve key and tempo fit: call `plan_mixes(track_ids, "sequence")` and prefer swaps that keep the arc and raise the pair scores. The arc wins when they conflict, unless a pair would clash badly (different keys and tempo gap over 10%); then swap that pair's order.
4. Record the final order with `state_set_plan` and `state_add_assumption("Arranged for a gentle build, a peak, then a wind-down")`.

## Length

Each full song is about 3 to 4 minutes. For a set of D minutes use about D / 3.5 songs. If a song is long, `extract_section` with `intro` or `drop` can shorten it before the medley.
