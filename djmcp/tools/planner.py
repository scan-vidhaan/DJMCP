"""Combination planning: rank ways to combine analyzed tracks into one mix.

Deterministic scoring (key compatibility on the Camelot wheel, tempo gap,
energy flow) so the agents' plans are repeatable and explainable; the agent
only chooses among, or explains, the ranked options.

A plan's steps are:
  {"type": "track", "track_id": ...}                       a whole song in the sequence
  {"type": "layered", "vocal": ..., "instrumental": ...}   a mashup segment
Transitions between consecutive steps carry a suggested crossfade length.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from djmcp.tools import analysis

MAX_EXACT_ORDERINGS = 7  # 7! = 5040 permutations; above this, greedy
MAX_TEMPO_GAP = 0.10
MAX_KEY_SHIFT = 3
_CAMELOT = re.compile(r"^(\d{1,2})([AB])$")


def camelot_score(a: str, b: str) -> float:
    """1.0 same key; 0.85 adjacent or relative major/minor; 0.6 two steps; else 0.25."""
    ma, mb = _CAMELOT.match(a or ""), _CAMELOT.match(b or "")
    if not ma or not mb:
        return 0.4  # unknown key: neither good nor bad
    na, la = int(ma.group(1)), ma.group(2)
    nb, lb = int(mb.group(1)), mb.group(2)
    step = min((na - nb) % 12, (nb - na) % 12)
    if step == 0:
        return 1.0 if la == lb else 0.85
    if step == 1 and la == lb:
        return 0.85
    if step == 2 and la == lb:
        return 0.6
    return 0.25


def tempo_gap(bpm_a: float, bpm_b: float) -> float:
    """Fractional tempo difference, treating half/double time as equivalent."""
    if bpm_a <= 0 or bpm_b <= 0:
        return 1.0
    return min(abs(bpm_b * f - bpm_a) / bpm_a for f in (0.5, 1.0, 2.0))


def tempo_score(gap: float) -> float:
    if gap <= 0.03:
        return 1.0
    if gap <= 0.06:
        return 0.8
    if gap <= MAX_TEMPO_GAP:
        return 0.5
    return 0.15


def _semitone_distance(key_a: str, key_b: str) -> int:
    diff = (analysis.pitch_class_of(key_b) - analysis.pitch_class_of(key_a)) % 12
    return diff - 12 if diff > 6 else diff


def _label(info: dict, titles: dict[str, str]) -> str:
    return titles.get(info["track_id"]) or info["track_id"][:24]


def _load(track_ids: list[str]) -> dict[str, dict]:
    infos = {}
    for track_id in track_ids:
        data = analysis.analyze_track(track_id)
        sections = data.get("sections", [])
        total = sum(s["end"] - s["start"] for s in sections) or 1.0
        energy = sum(s["energy"] * (s["end"] - s["start"]) for s in sections) / total
        infos[track_id] = {
            "track_id": track_id,
            "bpm": data["bpm"],
            "key": data["key"],
            "camelot": data["camelot"],
            "energy": energy,
            "duration": data.get("duration", 0.0),
        }
    return infos


def pair_score(a: dict, b: dict) -> dict:
    """How well b follows a in a sequence."""
    key = camelot_score(a["camelot"], b["camelot"])
    gap = tempo_gap(a["bpm"], b["bpm"])
    peak = max(a["energy"], b["energy"]) or 1.0
    energy = 1.0 - min(1.0, abs(a["energy"] - b["energy"]) / peak)
    return {
        "score": 0.4 * key + 0.4 * tempo_score(gap) + 0.2 * energy,
        "key": key,
        "tempo_gap": gap,
        "same_key": a["camelot"] == b["camelot"],
    }


def _transition_bars(gap: float) -> int:
    return 8 if gap < MAX_TEMPO_GAP else 2


def _sequence_plans(infos: dict[str, dict], ids: list[str], first: str | None = None) -> list[tuple[float, list[str]]]:
    """(score, ordering) pairs, best first. `first` pins the opening track."""
    if len(ids) < 2:
        return [(1.0, list(ids))]
    pair = {(a, b): pair_score(infos[a], infos[b])["score"] for a in ids for b in ids if a != b}

    def total(order: tuple[str, ...]) -> float:
        return sum(pair[(a, b)] for a, b in zip(order[:-1], order[1:])) / (len(order) - 1)

    if len(ids) <= MAX_EXACT_ORDERINGS:
        orders = [o for o in itertools.permutations(ids) if first is None or o[0] == first]
    else:
        orders = []
        for start in ([first] if first else ids):
            order, rest = [start], set(ids) - {start}
            while rest:
                nxt = max(rest, key=lambda t: pair[(order[-1], t)])
                order.append(nxt)
                rest.remove(nxt)
            orders.append(tuple(order))
    return sorted(((total(o), list(o)) for o in orders), key=lambda p: -p[0])


def _layered_score(vocal: dict, inst: dict) -> dict:
    """Score a vocal-over-instrumental pairing.

    A shift of up to MAX_KEY_SHIFT semitones puts the vocal exactly in the
    instrumental's key, so it counts as a full match (minus a small cost per
    semitone for pitch-shift artifacts). Past that the mashup tool leaves the
    vocal unshifted, so only the keys' natural Camelot compatibility counts.
    """
    shift = _semitone_distance(vocal["key"], inst["key"])
    gap = tempo_gap(vocal["bpm"], inst["bpm"])
    if abs(shift) <= MAX_KEY_SHIFT:
        key = 1.0 - 0.06 * abs(shift)
        applied = shift
    else:
        key = camelot_score(vocal["camelot"], inst["camelot"])
        applied = 0
    return {"score": 0.5 * key + 0.4 * tempo_score(gap) + 0.1, "key_shift": applied, "tempo_gap": gap}


def _describe_transition(a: dict, b: dict, titles: dict[str, str]) -> str:
    p = pair_score(a, b)
    key = "same key" if p["same_key"] else ("compatible keys" if p["key"] >= 0.85 else "different keys")
    return f"{_label(a, titles)} → {_label(b, titles)}: {key} ({a['camelot']}/{b['camelot']}), {p['tempo_gap']:.0%} tempo gap"


def plan_mixes(
    track_ids: list[str],
    mode: str = "both",
    top_k: int = 4,
    titles: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rank ways to combine 2+ analyzed tracks.

    mode: "sequence" (A then B then C), "layered" (one song's vocal over
    another's instrumental) or "both" (a layered opening, then the rest in
    sequence). Returns {"plans": [...]} best first; each plan has id, mode,
    summary, score, reason and steps.
    """
    if mode not in ("sequence", "layered", "both"):
        raise ValueError(f"mode must be sequence|layered|both, got {mode!r}")
    ids = list(dict.fromkeys(track_ids))
    if len(ids) < 2:
        raise ValueError("need at least 2 tracks to plan a mix")
    titles = titles or {}
    infos = _load(ids)
    plans: list[dict] = []

    def sequence_steps(order: list[str]) -> list[dict]:
        steps: list[dict] = []
        for i, track_id in enumerate(order):
            step: dict = {"type": "track", "track_id": track_id}
            if i > 0:
                step["transition_bars"] = _transition_bars(tempo_gap(infos[order[i - 1]]["bpm"], infos[track_id]["bpm"]))
            steps.append(step)
        return steps

    if mode == "sequence":
        for score, order in _sequence_plans(infos, ids)[:top_k]:
            plans.append(
                {
                    "mode": "sequence",
                    "summary": " → ".join(_label(infos[t], titles) for t in order),
                    "score": round(score, 3),
                    "reason": "; ".join(_describe_transition(infos[a], infos[b], titles) for a, b in zip(order[:-1], order[1:])),
                    "steps": sequence_steps(order),
                }
            )

    layered_pairs = sorted(
        ((_layered_score(infos[v], infos[i]), v, i) for v in ids for i in ids if v != i),
        key=lambda p: -p[0]["score"],
    )

    def layered_step(v: str, i: str, detail: dict) -> dict:
        return {"type": "layered", "vocal": v, "instrumental": i, "key_shift": detail["key_shift"], "tempo_gap": round(detail["tempo_gap"], 3)}

    def layered_reason(v: str, i: str, detail: dict) -> str:
        return (
            f"vocal of {_label(infos[v], titles)} over {_label(infos[i], titles)}: "
            f"{infos[v]['camelot']}/{infos[i]['camelot']}, key shift {detail['key_shift']:+d}, {detail['tempo_gap']:.0%} tempo gap"
        )

    if mode == "layered":
        for detail, v, i in layered_pairs[:top_k]:
            plans.append(
                {
                    "mode": "layered",
                    "summary": f"{_label(infos[v], titles)} (vocal) over {_label(infos[i], titles)}",
                    "score": round(detail["score"], 3),
                    "reason": layered_reason(v, i, detail),
                    "steps": [layered_step(v, i, detail)],
                }
            )

    if mode == "both":
        for detail, v, i in layered_pairs[: max(top_k, 3)]:
            rest = [t for t in ids if t not in (v, i)]
            if not rest:
                plans.append(
                    {
                        "mode": "both",
                        "summary": f"{_label(infos[v], titles)} (vocal) over {_label(infos[i], titles)}",
                        "score": round(detail["score"], 3),
                        "reason": layered_reason(v, i, detail),
                        "steps": [layered_step(v, i, detail)],
                    }
                )
                continue
            # The layered segment plays at the instrumental's tempo and key,
            # so score the hand-off to the rest as if it were that track.
            seq_ids = [i, *rest]
            seq_score, order = _sequence_plans(infos, seq_ids, first=i)[0]
            tail = order[1:]
            steps = [layered_step(v, i, detail)]
            prev = infos[i]
            for t in tail:
                steps.append({"type": "track", "track_id": t, "transition_bars": _transition_bars(tempo_gap(prev["bpm"], infos[t]["bpm"]))})
                prev = infos[t]
            plans.append(
                {
                    "mode": "both",
                    "summary": f"{_label(infos[v], titles)} (vocal) over {_label(infos[i], titles)} → "
                    + " → ".join(_label(infos[t], titles) for t in tail),
                    "score": round(0.5 * detail["score"] + 0.5 * seq_score, 3),
                    "reason": layered_reason(v, i, detail) + "; then "
                    + "; ".join(_describe_transition(infos[a], infos[b], titles) for a, b in zip(order[:-1], order[1:])),
                    "steps": steps,
                }
            )

    plans.sort(key=lambda p: -p["score"])
    plans = plans[:top_k]
    for n, plan in enumerate(plans, start=1):
        plan["id"] = f"p{n}"
    return {"plans": plans, "tracks": {t: {k: infos[t][k] for k in ("bpm", "camelot", "key", "energy")} for t in ids}}
