import pytest

from djmcp.tools import transcribe


async def test_transcribe_track_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        await transcribe.transcribe_track("does-not-exist-track-id")


def test_cache_path_matches_track_id():
    path = transcribe._cache_path("some-track-id")
    assert path.name == "some-track-id.transcript.json"
