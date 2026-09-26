import pytest
from pydub import AudioSegment

from djmcp.tools import analysis, edit


def test_trim_snap_to_beat_lands_on_beat_boundaries(synthetic_track):
    beat_times = analysis.analyze_track(synthetic_track)["beat_times"]
    # Deliberately off-beat requested bounds -- snapping should pull them
    # onto the nearest actual beats.
    result = edit.trim(synthetic_track, start_sec=beat_times[1] + 0.05, end_sec=beat_times[4] - 0.05)

    exported = AudioSegment.from_file(result["path"])
    expected_duration = beat_times[4] - beat_times[1]
    assert abs(exported.duration_seconds - expected_duration) < 0.1


def test_trim_without_snap_uses_exact_bounds(synthetic_track):
    result = edit.trim(synthetic_track, start_sec=1.0, end_sec=3.0, snap_to_beat=False)
    exported = AudioSegment.from_file(result["path"])
    assert abs(exported.duration_seconds - 2.0) < 0.05


def test_trim_rejects_reversed_bounds(synthetic_track):
    with pytest.raises(ValueError):
        edit.trim(synthetic_track, start_sec=5.0, end_sec=1.0, snap_to_beat=False)


def test_split_at_beats_returns_consecutive_pieces(synthetic_track):
    pieces = edit.split_at_beats(synthetic_track, beat_indices=[2, 5])
    assert len(pieces) == 3

    # Pieces should cover the whole track with no gaps/overlaps (within
    # mp3 encoder rounding).
    from djmcp.tools.common import resolve_track_path

    total_duration = sum(AudioSegment.from_file(p["path"]).duration_seconds for p in pieces)
    original_duration = AudioSegment.from_file(resolve_track_path(synthetic_track)).duration_seconds
    assert abs(total_duration - original_duration) < 0.2


def test_split_at_beats_rejects_empty_indices(synthetic_track):
    with pytest.raises(ValueError):
        edit.split_at_beats(synthetic_track, beat_indices=[])


@pytest.mark.parametrize("section_name", ["intro", "drop", "breakdown", "outro"])
def test_extract_section_produces_valid_clip(synthetic_track, section_name):
    result = edit.extract_section(synthetic_track, section_name)
    exported = AudioSegment.from_file(result["path"])
    assert exported.duration_seconds > 0


def test_extract_section_rejects_unknown_name(synthetic_track):
    with pytest.raises(ValueError):
        edit.extract_section(synthetic_track, "chorus")
