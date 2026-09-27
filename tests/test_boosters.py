import numpy as np
import pytest
from pydub import AudioSegment

from djmcp.tools import boosters


def _peak_dbfs_of(path: str) -> float:
    return AudioSegment.from_file(path).max_dBFS


def _rms_of(path: str) -> float:
    audio = AudioSegment.from_file(path)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float64)
    return float(np.sqrt(np.mean(samples**2)))


def test_bass_boost_changes_audio_without_clipping(synthetic_track):
    from djmcp.tools.common import resolve_track_path

    original_rms = _rms_of(str(resolve_track_path(synthetic_track)))
    result = boosters.bass_boost(synthetic_track, gain_db=6.0)
    assert _rms_of(result["path"]) != original_rms
    assert _peak_dbfs_of(result["path"]) <= -0.9


def test_energy_lift_changes_audio_without_clipping(synthetic_track):
    from djmcp.tools.common import resolve_track_path

    original_rms = _rms_of(str(resolve_track_path(synthetic_track)))
    result = boosters.energy_lift(synthetic_track, amount=0.8)
    assert _rms_of(result["path"]) != original_rms
    assert _peak_dbfs_of(result["path"]) <= -0.9


def test_energy_lift_clamps_amount_out_of_range(synthetic_track):
    # amount is clamped to [0, 1] rather than raising -- shouldn't crash on
    # an out-of-range caller value.
    result = boosters.energy_lift(synthetic_track, amount=5.0)
    assert _peak_dbfs_of(result["path"]) <= -0.9


@pytest.mark.integration
async def test_vocal_boost_via_demucs(synthetic_track):
    result = await boosters.vocal_boost(synthetic_track, gain_db=6.0)
    assert _peak_dbfs_of(result["path"]) <= -0.9
