"""Mixing: crossfade, medley, overlay_loop, mashup.

mashup needs demucs (stem separation) -- see djmcp/tools/stems.py, imported
lazily since it pulls in PyTorch.
"""

from __future__ import annotations

import asyncio
import json
import logging

import librosa
import numpy as np

from djmcp.config import LOOPS_DIR, TRACKS_DIR
from djmcp.tools import analysis
from djmcp.tools.dsp import load_audio, new_track_id, save_audio

logger = logging.getLogger(__name__)

BEATS_PER_BAR = 4
MAX_TEMPO_DRIFT = 0.10
MAX_KEY_SHIFT_SEMITONES = 3
VOCAL_TARGET_DBFS = -6.0


def _manifest() -> list[dict]:
    return json.loads((LOOPS_DIR / "manifest.json").read_text(encoding="utf-8"))


def crossfade(track_a_id: str, track_b_id: str, bars: int = 8) -> dict:
    """Blend from track_a into track_b over `bars` bars, beat-matched if tempo drift is small.

    Both tracks' lead-ins (before their own first detected beat) are
    trimmed first so the crossfade region starts on-beat for both --
    a simplified stand-in for full downbeat detection.
    """
    analysis_a = analysis.analyze_track(track_a_id)
    analysis_b = analysis.analyze_track(track_b_id)
    bpm_a, bpm_b = analysis_a["bpm"], analysis_b["bpm"]

    y_a, sr_a = load_audio(track_a_id)
    y_b, sr_b = load_audio(track_b_id)
    if sr_b != sr_a:
        y_b = librosa.resample(y_b, orig_sr=sr_b, target_sr=sr_a)

    drift = abs(bpm_b - bpm_a) / bpm_a if bpm_a else 0.0
    if drift < MAX_TEMPO_DRIFT and bpm_b > 0:
        y_b = librosa.effects.time_stretch(y_b, rate=bpm_a / bpm_b)

    first_beat_a = analysis_a["beat_times"][0] if analysis_a["beat_times"] else 0.0
    first_beat_b = analysis_b["beat_times"][0] if analysis_b["beat_times"] else 0.0
    y_a = y_a[int(first_beat_a * sr_a) :]
    y_b = y_b[int(first_beat_b * sr_a) :]

    crossfade_sec = bars * BEATS_PER_BAR * (60.0 / bpm_a) if bpm_a else 0.0
    crossfade_samples = min(int(crossfade_sec * sr_a), len(y_a), len(y_b))
    if crossfade_samples <= 0:
        raise ValueError("crossfade region resolved to zero samples -- check bars/bpm")

    a_head = y_a[:-crossfade_samples]
    a_tail = y_a[-crossfade_samples:]
    b_head = y_b[:crossfade_samples]
    b_tail = y_b[crossfade_samples:]

    fade_out = np.linspace(1.0, 0.0, crossfade_samples)
    fade_in = np.linspace(0.0, 1.0, crossfade_samples)
    blended = a_tail * fade_out + b_head * fade_in

    mixed = np.concatenate([a_head, blended, b_tail])
    new_id = new_track_id(track_a_id, "crossfade", track_b_id, bars)
    return save_audio(mixed, sr_a, new_id)


def medley(track_ids: list[str], bars: int = 8) -> dict:
    """Chain tracks A -> B -> C... with a crossfade between each pair.

    Pairs more than MAX_TEMPO_DRIFT apart in tempo cannot be beat-matched, so
    they get a short 2-bar blend instead of a long one that would sound like
    two songs fighting.
    """
    if len(track_ids) < 2:
        raise ValueError("medley needs at least 2 tracks")
    current = track_ids[0]
    transitions = []
    result: dict = {}
    for nxt in track_ids[1:]:
        bpm_a = analysis.analyze_track(current)["bpm"]
        bpm_b = analysis.analyze_track(nxt)["bpm"]
        drift = abs(bpm_b - bpm_a) / bpm_a if bpm_a else 0.0
        pair_bars = bars if drift < MAX_TEMPO_DRIFT else min(bars, 2)
        result = crossfade(current, nxt, pair_bars)
        transitions.append({"to": nxt, "bars": pair_bars, "tempo_drift": round(drift, 3)})
        current = result["track_id"]
    return {**result, "transitions": transitions}


def overlay_loop(track_id: str, loop_name: str, bars: int, start_beat: int = 0) -> dict:
    """Time-stretch a bundled loop to the track's BPM and layer it in at start_beat."""
    loop_meta = next((m for m in _manifest() if m["name"] == loop_name), None)
    if loop_meta is None:
        available = [m["name"] for m in _manifest()]
        raise ValueError(f"unknown loop_name={loop_name!r}; available: {available}")

    track_info = analysis.analyze_track(track_id)
    beat_times = track_info["beat_times"]
    if not (0 <= start_beat < len(beat_times)):
        raise ValueError(f"start_beat {start_beat} out of range (track has {len(beat_times)} beats)")

    y, sr = load_audio(track_id)
    loop_path = LOOPS_DIR / loop_meta["file"]
    loop_y, _ = librosa.load(str(loop_path), sr=sr, mono=True)

    track_bpm = track_info["bpm"]
    loop_bpm = loop_meta["bpm"]
    if loop_bpm > 0 and track_bpm > 0:
        loop_y = librosa.effects.time_stretch(loop_y, rate=track_bpm / loop_bpm)

    bar_sec = BEATS_PER_BAR * 60.0 / track_bpm if track_bpm else 0.0
    total_samples = int(bar_sec * bars * sr)
    if total_samples <= 0 or len(loop_y) == 0:
        raise ValueError("resolved overlay length is zero -- check bars/bpm")
    reps = int(np.ceil(total_samples / len(loop_y)))
    tiled_loop = np.tile(loop_y, reps)[:total_samples]

    start_sample = int(beat_times[start_beat] * sr)
    end_sample = min(start_sample + len(tiled_loop), len(y))

    mixed = y.copy()
    mixed[start_sample:end_sample] += tiled_loop[: end_sample - start_sample] * 0.8

    new_id = new_track_id(track_id, "overlay", loop_name, bars, start_beat)
    return save_audio(mixed, sr, new_id)


def _semitone_shift_to_match(from_key: str, to_key: str) -> int:
    """Shortest signed semitone distance from from_key's pitch class to to_key's."""
    diff = (analysis.pitch_class_of(to_key) - analysis.pitch_class_of(from_key)) % 12
    if diff > 6:
        diff -= 12
    return diff


def _load_lyric_lines(track_id: str) -> list[dict]:
    """Segments from the transcribe_track sidecar, or [] if the track wasn't transcribed."""
    sidecar = TRACKS_DIR / f"{track_id}.transcript.json"
    if not sidecar.exists():
        return []
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")).get("segments", [])
    except (OSError, ValueError):
        return []


def _snap_to_lines(lines: list[dict], start: float, end: float) -> tuple[float, float]:
    """Move [start, end] outward to lyric-line boundaries so a vocal never
    starts or stops mid-line: start -> start of the line containing it (or the
    next line), end -> end of the line containing it (or the previous line)."""
    if not lines:
        return start, end
    new_start = next((l["start"] for l in lines if l["end"] > start), lines[-1]["start"])
    new_end = next((l["end"] for l in reversed(lines) if l["start"] < end), lines[0]["end"])
    if new_end <= new_start:
        return start, end
    return new_start, new_end


def _stretch_rate(from_bpm: float, to_bpm: float) -> float:
    """Time-stretch rate that brings from_bpm onto to_bpm, treating half/double
    tempo as equivalent (beat trackers often lock onto the wrong octave).
    1.0 when either BPM is unknown or the tempos are too far apart to stretch cleanly."""
    if from_bpm <= 0 or to_bpm <= 0:
        return 1.0
    best = min((from_bpm * f for f in (0.5, 1.0, 2.0)), key=lambda b: abs(b - to_bpm))
    rate = to_bpm / best
    return rate if abs(rate - 1.0) < MAX_TEMPO_DRIFT else 1.0


def _apply_edge_fades(y: np.ndarray, fade_in: int, fade_out: int) -> np.ndarray:
    """Smoothstep fade in/out over the first/last samples."""
    y = y.copy()
    if fade_in > 0 and len(y):
        t = np.linspace(0.0, 1.0, min(fade_in, len(y)))
        y[: len(t)] *= t * t * (3 - 2 * t)
    if fade_out > 0 and len(y):
        t = np.linspace(1.0, 0.0, min(fade_out, len(y)))
        y[len(y) - len(t) :] *= t * t * (3 - 2 * t)
    return y


def _mashup_blocking(
    vocal_track_id: str,
    instrumental_track_id: str,
    vocal_start_sec: float | None = None,
    vocal_end_sec: float | None = None,
) -> dict:
    from djmcp.tools import stems  # lazy: pulls in torch

    vocal_stems = stems.separate(vocal_track_id)
    vocal_y = stems._to_mono_numpy(vocal_stems["vocals"])
    sr = stems._get_separator().samplerate

    # instrumental_track_id is a normal song too, not a pre-stripped
    # instrumental -- separate it as well and drop its own vocal stem, or
    # the mashup would layer two sets of vocals on top of each other.
    inst_stems = stems.separate(instrumental_track_id)
    inst_only = sum(wave for name, wave in inst_stems.items() if name != "vocals")
    inst_y = stems._to_mono_numpy(inst_only)

    vocal_info = analysis.analyze_track(vocal_track_id)
    inst_info = analysis.analyze_track(instrumental_track_id)

    shift = _semitone_shift_to_match(vocal_info["key"], inst_info["key"])
    shift = max(-MAX_KEY_SHIFT_SEMITONES, min(MAX_KEY_SHIFT_SEMITONES, shift))
    if shift != 0:
        vocal_y = librosa.effects.pitch_shift(vocal_y, sr=sr, n_steps=shift)

    # Match tempo, otherwise the vocal drifts off the instrumental's grid.
    rate = _stretch_rate(vocal_info["bpm"], inst_info["bpm"])
    if rate != 1.0:
        vocal_y = librosa.effects.time_stretch(vocal_y, rate=rate)

    def vt(t: float) -> float:  # vocal-track time -> time in the stretched vocal
        return t / rate

    # Choose the vocal window and snap it to lyric lines (when the track was
    # transcribed) so the first word is never clipped and no line is cut off.
    lines = _load_lyric_lines(vocal_track_id)
    vocal_first_beat = vocal_info["beat_times"][0] if vocal_info["beat_times"] else 0.0
    win_start = vocal_start_sec
    if win_start is None:
        win_start = lines[0]["start"] if lines else vocal_first_beat
    if vocal_end_sec is not None:
        win_end = vocal_end_sec
    else:
        win_end = lines[-1]["end"] if lines else len(vocal_y) / sr * rate
    win_start, win_end = _snap_to_lines(lines, win_start, win_end)

    inst_beats = inst_info["beat_times"]
    beat_sec = 60.0 / inst_info["bpm"] if inst_info["bpm"] else 0.5
    bar_sec = BEATS_PER_BAR * beat_sec
    fade_sec = min(2 * beat_sec, 2.0)

    # Anchor the nearest vocal beat to an instrumental downbeat one bar in, so
    # the vocal keeps its groove relative to the beat and enters after the
    # instrumental has set the scene instead of at sample zero.
    vocal_beats = [vt(b) for b in vocal_info["beat_times"]] or [vt(win_start)]
    ws = vt(win_start)
    anchor_vocal = min(vocal_beats, key=lambda b: abs(b - ws))
    first_inst_beat = inst_beats[0] if inst_beats else 0.0
    anchor_inst = first_inst_beat + bar_sec
    # The ramp-in runs through the stem's quiet gap before the first word, so
    # the word itself arrives at full level.
    seg_start_sec = max(0.0, ws - fade_sec)
    seg_end_sec = min(len(vocal_y) / sr, vt(win_end) + fade_sec)
    segment = vocal_y[int(seg_start_sec * sr) : int(seg_end_sec * sr)]
    segment = _apply_edge_fades(segment, int(fade_sec * sr), int(fade_sec * sr))

    place_sec = anchor_inst + (seg_start_sec - anchor_vocal)
    if place_sec < 0:  # window would start before the song does: trim the head
        segment = segment[int(-place_sec * sr) :]
        place_sec = 0.0
    entry_sec = place_sec + (ws - seg_start_sec)
    vocal_full = np.concatenate([np.zeros(int(place_sec * sr)), segment])

    vocal_peak = float(np.max(np.abs(vocal_full))) + 1e-9
    vocal_full = vocal_full / vocal_peak * (10 ** (VOCAL_TARGET_DBFS / 20))

    length = max(len(vocal_full), len(inst_y))
    mixed = np.pad(vocal_full, (0, length - len(vocal_full))) + np.pad(inst_y, (0, length - len(inst_y)))
    mixed = _apply_edge_fades(mixed, 0, int(min(4 * beat_sec, 3.0) * sr))  # gentle ending

    new_id = new_track_id(vocal_track_id, "mashup", instrumental_track_id, round(win_start, 2), round(win_end, 2))
    result = save_audio(mixed, sr, new_id)
    result.update(
        {
            "vocal_entry_sec": round(entry_sec, 2),
            "vocal_window": [round(win_start, 2), round(win_end, 2)],
            "key_shift_semitones": shift,
            "tempo_stretch": round(rate, 3),
        }
    )
    return result


async def mashup(
    vocal_track_id: str,
    instrumental_track_id: str,
    vocal_start_sec: float | None = None,
    vocal_end_sec: float | None = None,
) -> dict:
    """demucs-isolate the vocal from vocal_track_id and the non-vocal stems
    from instrumental_track_id (both are normal songs, not pre-stripped
    instrumentals); key-shift and tempo-match the vocal, then enter it on an
    instrumental downbeat one bar in, with fades and lyric-line-aligned edges
    (uses the transcript sidecar when transcribe_track has been run).

    vocal_start_sec / vocal_end_sec pick which part of the vocal song to use
    (default: all of it). Slow (stem separation on both tracks); call via a
    background job.
    """
    return await asyncio.to_thread(
        _mashup_blocking, vocal_track_id, instrumental_track_id, vocal_start_sec, vocal_end_sec
    )
