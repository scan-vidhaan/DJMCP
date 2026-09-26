"""Shared test fixtures.

analyze_track / edit.* need a real audio file to run against. Rather than
bundling a copyrighted or externally-sourced fixture, we synthesize a short
click track at a known BPM -- this gives deterministic, license-free audio
that also makes the BPM checkpoint ("detected BPM within +/-2 of ground
truth") directly testable.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf
from pydub import AudioSegment

KNOWN_BPM = 120
FIXTURE_DURATION_SEC = 12
SAMPLE_RATE = 22050


def _make_click_track_mp3(path, bpm: int, duration_sec: float, sr: int) -> None:
    beat_interval = 60.0 / bpm
    n_samples = int(duration_sec * sr)
    audio = np.zeros(n_samples, dtype=np.float64)

    click_dur = 0.05
    click_samples = int(click_dur * sr)
    t = np.linspace(0, click_dur, click_samples, endpoint=False)
    click = np.sin(2 * np.pi * 1000 * t) * np.exp(-30 * t)

    beat_time = 0.0
    while beat_time < duration_sec:
        start = int(beat_time * sr)
        end = min(start + click_samples, n_samples)
        audio[start:end] += click[: end - start]
        beat_time += beat_interval

    audio = audio / (np.max(np.abs(audio)) + 1e-9) * 0.8
    audio_int16 = (audio * 32767).astype(np.int16)

    wav_path = path.with_suffix(".wav")
    sf.write(str(wav_path), audio_int16, sr, subtype="PCM_16")
    AudioSegment.from_wav(str(wav_path)).export(str(path), format="mp3", bitrate="192k")
    wav_path.unlink()


@pytest.fixture
def synthetic_track(monkeypatch, tmp_path):
    """A synthetic click-track track_id, with TRACKS_DIR/PROCESSED_DIR redirected to tmp_path."""
    tracks_dir = tmp_path / "tracks"
    processed_dir = tmp_path / "processed"
    tracks_dir.mkdir()
    processed_dir.mkdir()

    # Each of these modules imported TRACKS_DIR/PROCESSED_DIR by name at
    # import time, so the redirect has to happen on each module's own
    # namespace, not on djmcp.config.
    import djmcp.tools.analysis as analysis_mod
    import djmcp.tools.common as common_mod
    import djmcp.tools.edit as edit_mod

    monkeypatch.setattr(common_mod, "TRACKS_DIR", tracks_dir)
    monkeypatch.setattr(common_mod, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(analysis_mod, "TRACKS_DIR", tracks_dir)
    monkeypatch.setattr(edit_mod, "PROCESSED_DIR", processed_dir)

    track_id = "synthetic-click-track"
    _make_click_track_mp3(tracks_dir / f"{track_id}.mp3", KNOWN_BPM, FIXTURE_DURATION_SEC, SAMPLE_RATE)
    return track_id
