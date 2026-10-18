from __future__ import annotations

import pytest
from pydub import AudioSegment

from djmcp.tools import export


@pytest.fixture
def exports_dir(monkeypatch, tmp_path):
    out = tmp_path / "exports"
    out.mkdir()
    monkeypatch.setattr(export, "EXPORTS_DIR", out)
    return out


def test_export_mp3_writes_file(synthetic_track, exports_dir):
    result = export.export_mp3(synthetic_track, bitrate=128)
    assert (exports_dir / f"{synthetic_track}.mp3").exists()
    assert result["duration"] > 10


def test_short_clip_duration(synthetic_track, exports_dir):
    result = export.short_clip(synthetic_track, duration=6, format="tiktok")
    clip = AudioSegment.from_file(result["path"])
    assert 5.5 < clip.duration_seconds < 6.5


def test_short_clip_rejects_bad_format(synthetic_track, exports_dir):
    with pytest.raises(ValueError):
        export.short_clip(synthetic_track, format="vhs")


def test_missing_track(exports_dir):
    with pytest.raises(FileNotFoundError):
        export.export_mp3("nope")
