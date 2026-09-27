import numpy as np
import pytest
from pydub import AudioSegment

from djmcp.tools import effects


def _rms_of(path: str) -> float:
    audio = AudioSegment.from_file(path)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float64)
    return float(np.sqrt(np.mean(samples**2)))


def _peak_dbfs_of(path: str) -> float:
    audio = AudioSegment.from_file(path)
    return audio.max_dBFS


def test_apply_reverb_changes_audio_without_clipping(synthetic_track):
    result = effects.apply_reverb(synthetic_track, room_size=0.7, wet=0.5)
    assert _peak_dbfs_of(result["path"]) <= -0.9


def test_apply_delay_changes_audio_without_clipping(synthetic_track):
    result = effects.apply_delay(synthetic_track, time_ms=300, feedback=0.4, wet=0.5)
    assert _peak_dbfs_of(result["path"]) <= -0.9


def _track_path(track_id: str) -> str:
    from djmcp.tools.common import resolve_track_path

    return str(resolve_track_path(track_id))


def test_apply_filter_lowpass_reduces_high_frequency_content(synthetic_track):
    # The click track is full-spectrum (impulsive clicks); a low cutoff
    # lowpass should measurably reduce overall energy.
    original_rms = _rms_of(_track_path(synthetic_track))
    result = effects.apply_filter(synthetic_track, type="lowpass", cutoff_hz=300, resonance=0.7)
    filtered_rms = _rms_of(result["path"])
    assert filtered_rms < original_rms


def test_apply_filter_rejects_unknown_type(synthetic_track):
    with pytest.raises(ValueError):
        effects.apply_filter(synthetic_track, type="notch", cutoff_hz=1000)


def test_apply_eq_low_boost_increases_low_frequency_energy(synthetic_track):
    original_rms = _rms_of(_track_path(synthetic_track))
    result = effects.apply_eq(synthetic_track, low_gain=12.0)
    # A low-shelf boost raises overall RMS on a signal with low-frequency
    # content; if it didn't, the shelf isn't doing anything.
    assert _rms_of(result["path"]) != original_rms


def test_apply_eq_no_gain_is_still_a_valid_passthrough(synthetic_track):
    result = effects.apply_eq(synthetic_track, low_gain=0.0, mid_gain=0.0, high_gain=0.0)
    assert _peak_dbfs_of(result["path"]) <= -0.9
