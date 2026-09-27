"""Track analysis: BPM, key, beat grid, and section boundaries.

Feeds djmcp/tools/edit.py (beat-snapped trims, section extraction) and the
orchestrating agent's remix decisions. Cached as a JSON sidecar next to the
track (same pattern transcribe.py uses) since librosa analysis is slow
enough that re-running it on every call would be wasteful.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import librosa
import numpy as np

from djmcp.config import TRACKS_DIR
from djmcp.tools.common import resolve_track_path

logger = logging.getLogger(__name__)

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler key profiles: relative perceived stability of each
# pitch class within a major/minor tonal context, starting from the tonic.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

# Camelot wheel position by (pitch class, mode). Standard harmonic-mixing
# notation DJs use -- see the harmonic-mixing skill added in a later phase.
_MAJOR_CAMELOT = {0: 8, 1: 3, 2: 10, 3: 5, 4: 12, 5: 7, 6: 2, 7: 9, 8: 4, 9: 11, 10: 6, 11: 1}
_MINOR_CAMELOT = {0: 5, 1: 12, 2: 7, 3: 2, 4: 9, 5: 4, 6: 11, 7: 6, 8: 1, 9: 8, 10: 3, 11: 10}

MAX_SECTIONS = 8


def pitch_class_of(key: str) -> int:
    """Map a key string like "C" or "Am" to a pitch class 0-11 (mode ignored)."""
    note = key[:-1] if key.endswith("m") else key
    return _NOTE_NAMES.index(note)

# librosa's default hop_length (512) quantizes frame times coarsely enough
# to bias tempo estimation on tightly, evenly-spaced onsets (confirmed on a
# synthetic click track: 512 -> 117.5 BPM vs a true 120; 256 -> 120.2 BPM).
# Finer hop resolution also means more precise beat times for edit.py's
# beat-snapping, so this is a net improvement, not just a test workaround.
HOP_LENGTH = 256


def _cache_path(track_id: str) -> Path:
    return TRACKS_DIR / f"{track_id}.analysis.json"


def _detect_key(chroma_mean: np.ndarray) -> tuple[str, str]:
    """Krumhansl-Schmuckler: correlate the track's average chroma vector
    against all 24 rotated major/minor profiles, pick the best match."""
    best_score = -np.inf
    best_pitch_class = 0
    best_mode = "major"

    for pitch_class in range(12):
        major_rotated = np.roll(_MAJOR_PROFILE, pitch_class)
        minor_rotated = np.roll(_MINOR_PROFILE, pitch_class)
        major_score = np.corrcoef(chroma_mean, major_rotated)[0, 1]
        minor_score = np.corrcoef(chroma_mean, minor_rotated)[0, 1]

        if major_score > best_score:
            best_score, best_pitch_class, best_mode = major_score, pitch_class, "major"
        if minor_score > best_score:
            best_score, best_pitch_class, best_mode = minor_score, pitch_class, "minor"

    note = _NOTE_NAMES[best_pitch_class]
    if best_mode == "major":
        key = note
        camelot = f"{_MAJOR_CAMELOT[best_pitch_class]}B"
    else:
        key = f"{note}m"
        camelot = f"{_MINOR_CAMELOT[best_pitch_class]}A"
    return key, camelot


def _section_count(duration_sec: float) -> int:
    """More sections for longer tracks, capped so short clips don't over-split."""
    return max(2, min(MAX_SECTIONS, round(duration_sec / 30)))


def analyze_track(track_id: str, force: bool = False) -> dict:
    """Analyze a downloaded track: BPM, key, beat grid, sections. Cached."""
    cache_path = _cache_path(track_id)
    if not force and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    audio_path = resolve_track_path(track_id)
    if audio_path is None:
        raise FileNotFoundError(f"no downloaded track for track_id={track_id!r}")

    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = float(librosa.get_duration(y=y, sr=sr))

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=HOP_LENGTH)
    bpm = float(np.atleast_1d(tempo)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH).tolist()

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
    key, camelot = _detect_key(chroma.mean(axis=1))

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP_LENGTH)
    n_sections = _section_count(duration)
    bound_frames = librosa.segment.agglomerative(mfcc, k=n_sections)
    bound_times = librosa.frames_to_time(bound_frames, sr=sr, hop_length=HOP_LENGTH)
    bound_times = np.unique(np.concatenate([[0.0], bound_times, [duration]]))

    rms = librosa.feature.rms(y=y, hop_length=HOP_LENGTH)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)

    sections = []
    for start, end in zip(bound_times[:-1], bound_times[1:]):
        mask = (rms_times >= start) & (rms_times < end)
        energy = float(rms[mask].mean()) if mask.any() else 0.0
        sections.append({"start": round(float(start), 2), "end": round(float(end), 2), "energy": round(energy, 4)})

    result = {
        "track_id": track_id,
        "bpm": round(bpm, 1),
        "key": key,
        "camelot": camelot,
        "duration": round(duration, 2),
        "beat_times": [round(t, 3) for t in beat_times],
        "sections": sections,
    }
    cache_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
