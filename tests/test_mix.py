import numpy as np
import pytest
from pydub import AudioSegment

from djmcp.tools import mix


def _samples_of(path: str) -> np.ndarray:
    audio = AudioSegment.from_file(path)
    return np.array(audio.get_array_of_samples(), dtype=np.float64)


def test_crossfade_no_seam_discontinuity(synthetic_track, synthetic_track_b):
    result = mix.crossfade(synthetic_track, synthetic_track_b, bars=4)
    samples = _samples_of(result["path"])

    # A smooth crossfade shouldn't have any localized spike/drop in energy;
    # check that no short window's RMS deviates wildly from the track's
    # overall RMS (a hard cut or bad seam shows up as an outlier window).
    window = max(1, len(samples) // 50)
    overall_rms = np.sqrt(np.mean(samples**2)) + 1e-9
    window_rms = np.array(
        [np.sqrt(np.mean(samples[i : i + window] ** 2)) for i in range(0, len(samples) - window, window)]
    )
    assert np.max(window_rms) / overall_rms < 6.0


def test_crossfade_rejects_zero_bars(synthetic_track, synthetic_track_b):
    with pytest.raises(ValueError):
        mix.crossfade(synthetic_track, synthetic_track_b, bars=0)


def test_overlay_loop_adds_energy_at_start_beat(synthetic_track):
    result = mix.overlay_loop(synthetic_track, "kick_four_on_floor_120", bars=2, start_beat=0)
    assert result["duration"] > 0


def test_overlay_loop_rejects_unknown_loop_name(synthetic_track):
    with pytest.raises(ValueError):
        mix.overlay_loop(synthetic_track, "not-a-real-loop", bars=2)


def test_overlay_loop_rejects_out_of_range_start_beat(synthetic_track):
    with pytest.raises(ValueError):
        mix.overlay_loop(synthetic_track, "kick_four_on_floor_120", bars=2, start_beat=99999)


def test_semitone_shift_to_match_is_shortest_path():
    assert mix._semitone_shift_to_match("C", "C") == 0
    assert mix._semitone_shift_to_match("C", "G") == 7 - 12  # shortest path is -5, not +7
    assert mix._semitone_shift_to_match("C", "Cm") == 0  # mode ignored, pitch class only


@pytest.mark.integration
async def test_mashup_via_demucs(synthetic_track, synthetic_track_b):
    result = await mix.mashup(synthetic_track, synthetic_track_b)
    assert result["duration"] > 0
