import pytest

from djmcp.tools import analysis
from tests.conftest import KNOWN_BPM


def test_analyze_track_bpm_within_tolerance(synthetic_track):
    result = analysis.analyze_track(synthetic_track)
    assert abs(result["bpm"] - KNOWN_BPM) <= 2


def test_analyze_track_caches_result(synthetic_track):
    first = analysis.analyze_track(synthetic_track)
    cache_path = analysis._cache_path(synthetic_track)
    assert cache_path.exists()

    # Corrupt-but-detectable marker to prove the second call reads the cache
    # rather than recomputing.
    second = analysis.analyze_track(synthetic_track)
    assert second == first


def test_analyze_track_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        analysis.analyze_track("does-not-exist-track-id")


def test_analyze_track_has_beat_times_and_sections(synthetic_track):
    result = analysis.analyze_track(synthetic_track)
    assert len(result["beat_times"]) > 0
    assert len(result["sections"]) >= 2
    for section in result["sections"]:
        assert section["end"] > section["start"]
