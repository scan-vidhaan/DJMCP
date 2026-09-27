"""Mixing: crossfade, overlay_loop, mashup.

mashup needs demucs (stem separation) -- see djmcp/tools/stems.py, imported
lazily since it pulls in PyTorch.
"""

from __future__ import annotations

import asyncio
import json
import logging

import librosa
import numpy as np

from djmcp.config import LOOPS_DIR
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


def _mashup_blocking(vocal_track_id: str, instrumental_track_id: str) -> dict:
    from djmcp.tools import stems  # lazy: pulls in torch

    vocal_stems = stems.separate(vocal_track_id)
    vocal_y = stems._to_mono_numpy(vocal_stems["vocals"])
    sr = stems._get_separator().samplerate

    inst_y, inst_sr = load_audio(instrumental_track_id)
    if inst_sr != sr:
        inst_y = librosa.resample(inst_y, orig_sr=inst_sr, target_sr=sr)

    vocal_info = analysis.analyze_track(vocal_track_id)
    inst_info = analysis.analyze_track(instrumental_track_id)

    shift = _semitone_shift_to_match(vocal_info["key"], inst_info["key"])
    shift = max(-MAX_KEY_SHIFT_SEMITONES, min(MAX_KEY_SHIFT_SEMITONES, shift))
    if shift != 0:
        vocal_y = librosa.effects.pitch_shift(vocal_y, sr=sr, n_steps=shift)

    # Align first downbeats: drop the vocal's lead-in, then pad it out so
    # its first beat lands on the instrumental's first beat.
    vocal_first_beat = vocal_info["beat_times"][0] if vocal_info["beat_times"] else 0.0
    inst_first_beat = inst_info["beat_times"][0] if inst_info["beat_times"] else 0.0
    vocal_y = vocal_y[int(vocal_first_beat * sr) :]
    pad_samples = int(inst_first_beat * sr)
    vocal_y = np.concatenate([np.zeros(pad_samples), vocal_y])

    vocal_peak = float(np.max(np.abs(vocal_y))) + 1e-9
    vocal_y = vocal_y / vocal_peak * (10 ** (VOCAL_TARGET_DBFS / 20))

    length = max(len(vocal_y), len(inst_y))
    vocal_padded = np.pad(vocal_y, (0, length - len(vocal_y)))
    inst_padded = np.pad(inst_y, (0, length - len(inst_y)))
    mixed = vocal_padded + inst_padded

    new_id = new_track_id(vocal_track_id, "mashup", instrumental_track_id)
    return save_audio(mixed, sr, new_id)


async def mashup(vocal_track_id: str, instrumental_track_id: str) -> dict:
    """demucs-isolate the vocal, key-shift + downbeat-align it to the instrumental, mix.

    Slow (stem separation); call via a background job.
    """
    return await asyncio.to_thread(_mashup_blocking, vocal_track_id, instrumental_track_id)
