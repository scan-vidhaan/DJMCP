from __future__ import annotations

import pytest

from djmcp.tools import analysis, planner

# id -> (bpm, key, camelot, energy)
FAKE = {
    "a": (120, "C", "8B", 0.10),
    "b": (122, "G", "9B", 0.12),   # adjacent key, near tempo: great after a
    "c": (126, "F#", "2B", 0.11),  # far key
    "d": (90, "C", "8B", 0.05),    # same key, slow
}


@pytest.fixture(autouse=True)
def fake_analysis(monkeypatch):
    def fake(track_id, force=False):
        bpm, key, camelot, energy = FAKE[track_id]
        return {
            "track_id": track_id, "bpm": bpm, "key": key, "camelot": camelot, "duration": 200.0,
            "sections": [{"start": 0.0, "end": 200.0, "energy": energy}],
        }

    monkeypatch.setattr(analysis, "analyze_track", fake)


def test_camelot_scores():
    assert planner.camelot_score("8B", "8B") == 1.0
    assert planner.camelot_score("8B", "9B") == 0.85
    assert planner.camelot_score("8B", "8A") == 0.85
    assert planner.camelot_score("12B", "1B") == 0.85  # the wheel wraps
    assert planner.camelot_score("8B", "2B") == 0.25
    assert planner.camelot_score("", "8B") == 0.4


def test_tempo_gap_treats_double_time_as_equal():
    assert planner.tempo_gap(70, 140) == pytest.approx(0.0)
    assert planner.tempo_gap(120, 126) == pytest.approx(0.05)
    assert planner.tempo_gap(0, 120) == 1.0


def test_sequence_puts_compatible_tracks_next_to_each_other():
    plans = planner.plan_mixes(["a", "b", "c"], "sequence")["plans"]
    best = [s["track_id"] for s in plans[0]["steps"]]
    assert abs(best.index("a") - best.index("b")) == 1  # a and b are the good pair
    assert plans[0]["score"] >= plans[-1]["score"]
    assert [p["id"] for p in plans] == [f"p{i}" for i in range(1, len(plans) + 1)]


def test_sequence_transition_bars_shrink_for_big_tempo_gaps():
    plan = planner.plan_mixes(["a", "d"], "sequence")["plans"][0]
    assert plan["steps"][1]["transition_bars"] == 2  # 120 vs 90 BPM: too far to blend long
    plan = planner.plan_mixes(["a", "b"], "sequence")["plans"][0]
    assert plan["steps"][1]["transition_bars"] == 8


def test_layered_prefers_small_key_shift_and_flags_it():
    plans = planner.plan_mixes(["a", "b", "c"], "layered")["plans"]
    top = plans[0]["steps"][0]
    assert {top["vocal"], top["instrumental"]} == {"a", "b"}
    assert abs(top["key_shift"]) <= 3
    far = [p for p in plans if "c" in (p["steps"][0]["vocal"], p["steps"][0]["instrumental"])]
    assert all(p["score"] < plans[0]["score"] for p in far)


def test_both_starts_with_layered_then_sequences_the_rest():
    plan = planner.plan_mixes(["a", "b", "c", "d"], "both")["plans"][0]
    assert plan["mode"] == "both"
    assert plan["steps"][0]["type"] == "layered"
    used = {plan["steps"][0]["vocal"], plan["steps"][0]["instrumental"]}
    rest = [s["track_id"] for s in plan["steps"][1:]]
    assert set(rest) == {"a", "b", "c", "d"} - used


def test_titles_appear_in_summary():
    plan = planner.plan_mixes(["a", "b"], "sequence", titles={"a": "Song A", "b": "Song B"})["plans"][0]
    assert "Song A" in plan["summary"] and "Song B" in plan["summary"]


def test_validation():
    with pytest.raises(ValueError):
        planner.plan_mixes(["a"], "sequence")
    with pytest.raises(ValueError):
        planner.plan_mixes(["a", "b"], "chaos")
    with pytest.raises(ValueError):
        planner.plan_mixes(["a", "a"], "sequence")  # duplicates collapse to one track


def test_many_tracks_use_greedy_and_still_return_plans(monkeypatch):
    ids = [f"t{i}" for i in range(9)]
    monkeypatch.setattr(
        analysis, "analyze_track",
        lambda tid, force=False: {"track_id": tid, "bpm": 120 + int(tid[1:]), "key": "C", "camelot": "8B",
                                  "duration": 200.0, "sections": [{"start": 0, "end": 200, "energy": 0.1}]},
    )
    plans = planner.plan_mixes(ids, "sequence")["plans"]
    assert plans and all(len(p["steps"]) == 9 for p in plans)
