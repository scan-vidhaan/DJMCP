---
name: harmonic-mixing
description: Camelot wheel key rules, tempo drift limits and key-shift limits for choosing which songs go together. Use when interpreting plan_mixes scores or explaining a pairing.
---

# Harmonic mixing

`plan_mixes` already scores every pairing; use this skill to read its output and explain it in plain words.

## Key compatibility (Camelot wheel)

| Relationship | Example | Verdict |
| --- | --- | --- |
| Same code | 8B and 8B | Perfect |
| One step around the wheel, same letter | 8B and 9B | Great |
| Same number, other letter (relative major/minor) | 8B and 8A | Great |
| Two steps, same letter | 8B and 10B | Workable |
| Anything else | 8B and 2B | Clashes; avoid blending, a cut is safer |

The wheel wraps: 12 is next to 1.

## Tempo

| Gap between songs | Meaning |
| --- | --- |
| 0 to 3% | Seamless |
| 3 to 6% | Smooth; the tool stretches one song to match |
| 6 to 10% | Noticeable stretch; still blendable |
| Over 10% | Cannot be beat-matched; use a short transition |

Half or double time counts as the same tempo (70 and 140 BPM match), because beat trackers often land on the wrong octave.

## Layered mashups and key shift

The vocal can be pitch-shifted up to 3 semitones to land exactly in the instrumental's key. Each semitone costs a little quality, so smaller shifts score higher. If matching would need more than 3 semitones, the vocal is left unshifted and only works when the two keys are already compatible on the wheel. The `key_shift` in a layered plan step is what will actually be applied.

## Explaining a pick

Give one short reason per choice, using the numbers in the plan's `reason`: "same key, 2% tempo gap" or "vocal shifted up 2 semitones to fit".
