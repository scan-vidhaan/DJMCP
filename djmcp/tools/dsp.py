"""Shared DSP helpers: load/save audio as numpy arrays, id generation, clipping guard."""

from __future__ import annotations

import hashlib

import librosa
import numpy as np
from pydub import AudioSegment

from djmcp.config import PROCESSED_DIR
from djmcp.tools.common import resolve_track_path

TARGET_PEAK_DBFS = -1.0


def load_audio(track_id: str) -> tuple[np.ndarray, int]:
    """Mono float array + sample rate for a track_id resolve_track_path can find."""
    audio_path = resolve_track_path(track_id)
    if audio_path is None:
        raise FileNotFoundError(f"no track found for track_id={track_id!r}")
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    return y, sr


def peak_normalize(y: np.ndarray, target_dbfs: float = TARGET_PEAK_DBFS) -> np.ndarray:
    """Scale so the peak sample sits at target_dbfs -- the clipping guard every
    effect/booster runs before export, since filters and gain stages can easily
    push samples past +-1.0."""
    peak = float(np.max(np.abs(y)))
    if peak < 1e-9:
        return y
    target_linear = 10 ** (target_dbfs / 20)
    return y / peak * target_linear


_MAX_SOURCE_ID_LEN = 40


def new_track_id(source_track_id: str, suffix: str, *parts: object) -> str:
    """A new id derived from source_track_id, bounded in length regardless of
    chain depth. Each id embeds only a truncated prefix of its immediate
    parent, not the parent's full (possibly already-chained) name -- without
    this, a run of several crossfade/trim/overlay calls in sequence grows
    the id by one "-<op>-<hash>" segment per step and eventually blows past
    Windows' ~260 char MAX_PATH once combined with the storage directory
    path, failing with a misleading FileNotFoundError on write.
    """
    digest = hashlib.sha1(f"{source_track_id}-{suffix}-{parts}".encode()).hexdigest()[:8]
    truncated_source = source_track_id[:_MAX_SOURCE_ID_LEN]
    return f"{truncated_source}-{suffix}-{digest}"


def save_audio(y: np.ndarray, sr: int, track_id: str) -> dict:
    """Peak-normalize, encode to 320kbps mp3 in storage/processed/, return {track_id, path, duration}."""
    y = peak_normalize(y)
    y_int16 = (np.clip(y, -1.0, 1.0) * 32767).astype(np.int16)
    segment = AudioSegment(y_int16.tobytes(), frame_rate=sr, sample_width=2, channels=1)

    out_path = PROCESSED_DIR / f"{track_id}.mp3"
    segment.export(str(out_path), format="mp3", bitrate="320k")
    return {"track_id": track_id, "path": str(out_path), "duration": segment.duration_seconds}
