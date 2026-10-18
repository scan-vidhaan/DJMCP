from __future__ import annotations

import numpy as np

from djmcp.tools import mix, quality
from djmcp.tools.dsp import save_audio

LINES = [
    {"start": 5.0, "end": 8.0, "text": "a"},
    {"start": 9.0, "end": 12.0, "text": "b"},
    {"start": 14.0, "end": 18.0, "text": "c"},
]


def test_snap_to_lines_expands_to_line_edges():
    assert mix._snap_to_lines(LINES, 6.0, 10.0) == (5.0, 12.0)


def test_snap_to_lines_start_in_gap_takes_next_line():
    assert mix._snap_to_lines(LINES, 12.5, 17.0) == (14.0, 18.0)


def test_snap_to_lines_without_transcript_is_unchanged():
    assert mix._snap_to_lines([], 3.0, 9.0) == (3.0, 9.0)


def test_stretch_rate_close_tempos():
    assert abs(mix._stretch_rate(120, 126) - 1.05) < 1e-6


def test_stretch_rate_treats_double_time_as_equivalent():
    assert abs(mix._stretch_rate(70, 140) - 1.0) < 1e-6  # 70 -> 140 is just a doubling
    assert abs(mix._stretch_rate(140, 72) - 72 / 70) < 1e-6  # ...and 140 halves to 70 -> 72


def test_stretch_rate_too_far_apart_is_not_stretched():
    assert mix._stretch_rate(100, 130) == 1.0
    assert mix._stretch_rate(0, 120) == 1.0


def test_edge_fades_start_and_end_silent_middle_untouched():
    y = np.ones(1000)
    out = mix._apply_edge_fades(y, 100, 100)
    assert out[0] == 0.0 and out[-1] == 0.0
    assert np.all(out[200:800] == 1.0)
    assert np.all(np.diff(out[:100]) >= 0)  # monotonic ramp up


def test_medley_chains_and_reports_transitions(synthetic_track, synthetic_track_b):
    result = mix.medley([synthetic_track, synthetic_track_b, synthetic_track], bars=2)
    assert len(result["transitions"]) == 2
    assert result["duration"] > 12


def test_medley_needs_two_tracks(synthetic_track):
    import pytest

    with pytest.raises(ValueError):
        mix.medley([synthetic_track])


def test_check_seams_flags_hard_cut(synthetic_dirs):
    sr = 22050
    loud = 0.8 * np.sin(2 * np.pi * 220 * np.arange(sr * 3) / sr)
    quiet = 0.02 * np.sin(2 * np.pi * 220 * np.arange(sr * 3) / sr)
    save_audio(np.concatenate([loud, quiet]), sr, "hard-cut")
    result = quality.check_seams("hard-cut")
    assert not result["passed"]
    assert any(abs(j["time_sec"] - 3.0) < 0.6 for j in result["jumps"])


def test_check_seams_passes_steady_audio(synthetic_dirs):
    sr = 22050
    tone = 0.5 * np.sin(2 * np.pi * 220 * np.arange(sr * 6) / sr)
    save_audio(tone, sr, "steady")
    assert quality.check_seams("steady")["passed"]


def test_key_shift_applied_only_when_within_limit():
    assert mix._resolve_key_shift("C", "D") == 2
    assert mix._resolve_key_shift("C", "A") == -3
    assert mix._resolve_key_shift("C", "G") == 0  # needs -5: leave the vocal alone, don't half-shift
    assert mix._resolve_key_shift("C", "F#") == 0
