"""Beat-aware editing: trim, split, and section extraction.

Operates on any track_id resolve_track_path can find (an original download
or a previously-processed output), using djmcp.tools.analysis's cached beat
grid and section boundaries to snap cuts musically instead of at arbitrary
sample offsets. Outputs always go to storage/processed/.
"""

from __future__ import annotations

import logging

from pydub import AudioSegment

from djmcp.config import PROCESSED_DIR
from djmcp.tools import analysis
from djmcp.tools.common import resolve_track_path
from djmcp.tools.dsp import new_track_id

logger = logging.getLogger(__name__)

SECTION_NAMES = ("intro", "drop", "breakdown", "outro")


def _export(audio: AudioSegment, track_id: str) -> dict:
    out_path = PROCESSED_DIR / f"{track_id}.mp3"
    audio.export(out_path, format="mp3", bitrate="320k")
    return {"track_id": track_id, "path": str(out_path), "duration": audio.duration_seconds}


def _nearest_beat(beat_times: list[float], target_sec: float) -> float:
    if not beat_times:
        return target_sec
    return min(beat_times, key=lambda t: abs(t - target_sec))


def _load_audio(track_id: str) -> AudioSegment:
    audio_path = resolve_track_path(track_id)
    if audio_path is None:
        raise FileNotFoundError(f"no track found for track_id={track_id!r}")
    return AudioSegment.from_file(audio_path)


def trim(track_id: str, start_sec: float, end_sec: float, snap_to_beat: bool = True) -> dict:
    """Cut [start_sec, end_sec) out of a track, optionally snapped to the nearest beat."""
    if snap_to_beat:
        beat_times = analysis.analyze_track(track_id)["beat_times"]
        start_sec = _nearest_beat(beat_times, start_sec)
        end_sec = _nearest_beat(beat_times, end_sec)
    if end_sec <= start_sec:
        raise ValueError(f"end_sec ({end_sec}) must be after start_sec ({start_sec})")

    audio = _load_audio(track_id)
    segment = audio[start_sec * 1000 : end_sec * 1000]
    new_id = new_track_id(track_id, "trim", round(start_sec, 3), round(end_sec, 3))
    return _export(segment, new_id)


def split_at_beats(track_id: str, beat_indices: list[int]) -> list[dict]:
    """Cut a track into consecutive pieces at the given beat-grid indices."""
    if not beat_indices:
        raise ValueError("beat_indices must be non-empty")

    beat_times = analysis.analyze_track(track_id)["beat_times"]
    audio = _load_audio(track_id)
    duration_sec = audio.duration_seconds

    cut_points = sorted({beat_times[i] for i in beat_indices if 0 <= i < len(beat_times)})
    boundaries = [0.0, *cut_points, duration_sec]

    results = []
    for i, (start_sec, end_sec) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        if end_sec <= start_sec:
            continue
        segment = audio[start_sec * 1000 : end_sec * 1000]
        new_id = new_track_id(track_id, f"split{i}", round(start_sec, 3), round(end_sec, 3))
        results.append(_export(segment, new_id))
    return results


def extract_section(track_id: str, section_name: str) -> dict:
    """Extract intro/drop/breakdown/outro using analyzed section boundaries + energy."""
    if section_name not in SECTION_NAMES:
        raise ValueError(f"section_name must be one of {SECTION_NAMES}, got {section_name!r}")

    sections = analysis.analyze_track(track_id)["sections"]
    if not sections:
        raise ValueError(f"no sections found for track_id={track_id!r}")

    if section_name == "intro":
        chosen = sections[0]
    elif section_name == "outro":
        chosen = sections[-1]
    else:
        # "drop" and "breakdown" are defined relative to the middle of the
        # track -- the first/last sections are the intro/outro, never these.
        middle = sections[1:-1] or sections
        if section_name == "drop":
            chosen = max(middle, key=lambda s: s["energy"])
        else:
            chosen = min(middle, key=lambda s: s["energy"])

    audio = _load_audio(track_id)
    segment = audio[chosen["start"] * 1000 : chosen["end"] * 1000]
    new_id = new_track_id(track_id, section_name, chosen["start"], chosen["end"])
    return _export(segment, new_id)
