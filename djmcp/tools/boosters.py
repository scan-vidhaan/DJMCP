"""Boosters: bass_boost, vocal_boost, energy_lift.

vocal_boost needs demucs (stem separation) -- installed as the optional
[boosters] extra since it pulls in PyTorch. bass_boost and energy_lift are
pure scipy/numpy and don't need it.
"""

from __future__ import annotations

import asyncio

import numpy as np
from scipy import signal

from djmcp.tools import effects
from djmcp.tools.dsp import load_audio, new_track_id, save_audio

# Envelope-follower compressor parameters for energy_lift. Fixed rather than
# exposed: "amount" is meant to be one intuitive knob, not a full compressor
# UI -- these interpolate from "barely there" to "noticeably punchier".
_COMPRESSOR_THRESHOLD_DB = -18.0
_COMPRESSOR_RATIO_RANGE = (1.5, 6.0)
_ATTACK_SEC = 0.005
_RELEASE_SEC = 0.15


def bass_boost(track_id: str, gain_db: float = 6.0) -> dict:
    """Low-shelf boost below ~200Hz -- a thin wrapper over apply_eq."""
    return effects.apply_eq(track_id, low_gain=gain_db, mid_gain=0.0, high_gain=0.0)


def _db_to_linear(db: float) -> float:
    return 10 ** (db / 20)


def _linear_to_db(x: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.maximum(x, 1e-9))


def _envelope_follower(y: np.ndarray, sr: int, attack_sec: float, release_sec: float) -> np.ndarray:
    """Smoothed absolute amplitude, tracking transients fast (attack) and
    settling slowly (release) -- the standard compressor sidechain signal."""
    attack_coeff = np.exp(-1.0 / (sr * attack_sec))
    release_coeff = np.exp(-1.0 / (sr * release_sec))
    abs_y = np.abs(y)
    envelope = np.empty_like(abs_y)
    level = 0.0
    for i, sample in enumerate(abs_y):
        coeff = attack_coeff if sample > level else release_coeff
        level = coeff * level + (1 - coeff) * sample
        envelope[i] = level
    return envelope


def _compress(y: np.ndarray, sr: int, threshold_db: float, ratio: float) -> np.ndarray:
    envelope_db = _linear_to_db(_envelope_follower(y, sr, _ATTACK_SEC, _RELEASE_SEC))
    over_threshold = np.maximum(envelope_db - threshold_db, 0.0)
    gain_reduction_db = over_threshold * (1 - 1 / ratio)
    gain = _db_to_linear(-gain_reduction_db)
    return y * gain


def energy_lift(track_id: str, amount: float = 0.5) -> dict:
    """Compressor (envelope follower) + high-shelf + light tanh saturation.

    amount in [0, 1] interpolates ratio and saturation drive together, so
    the caller has one intuitive knob instead of a full compressor UI.
    """
    y, sr = load_audio(track_id)
    amount = float(np.clip(amount, 0.0, 1.0))

    ratio = _COMPRESSOR_RATIO_RANGE[0] + amount * (_COMPRESSOR_RATIO_RANGE[1] - _COMPRESSOR_RATIO_RANGE[0])
    compressed = _compress(y, sr, _COMPRESSOR_THRESHOLD_DB, ratio)

    # Makeup gain: compression quietens peaks, so restore the original peak
    # level before the shelf/saturation stages shape the tone.
    orig_peak = np.max(np.abs(y)) + 1e-9
    comp_peak = np.max(np.abs(compressed)) + 1e-9
    compressed *= orig_peak / comp_peak

    shelved = effects._biquad_shelf("high_shelf", 4000.0, sr, gain_db=3.0 * amount)
    brightened = signal.sosfilt(shelved, compressed)

    drive = 1.0 + amount * 3.0
    saturated = np.tanh(brightened * drive) / np.tanh(drive)

    new_id = new_track_id(track_id, "energy", amount)
    return save_audio(saturated, sr, new_id)


async def vocal_boost(track_id: str, gain_db: float = 6.0) -> dict:
    """demucs split -> gain the vocal stem -> remix. Slow; call via a background job."""
    from djmcp.tools import stems  # imported lazily: demucs pulls in torch

    return await asyncio.to_thread(stems.boost_stem, track_id, "vocals", gain_db)
