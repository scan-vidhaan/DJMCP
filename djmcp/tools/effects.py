"""Audio effects: reverb, filter, delay, EQ -- scipy.signal + numpy only, no pedalboard.

Biquad coefficients follow the RBJ Audio EQ Cookbook (a standard, widely
published set of formulas for shelving/peaking/lowpass/highpass/bandpass
biquads; not tied to any particular library).

Comb/allpass filters (reverb, delay) are single-tap feedback IIRs at delays
of tens of milliseconds -- tens of thousands of samples. A naive per-sample
Python loop over a whole track would be too slow, and scipy.signal.lfilter
treats `a` as dense regardless of how many of its coefficients are actually
zero, so filtering directly with a length-D `a` array is O(N*D). Splitting
the signal into D interleaved "phase" subsequences (see _polyphase_iir)
turns each into an independent order-1 recursion scipy.signal.lfilter
handles at native speed, so the whole thing is O(N).
"""

from __future__ import annotations

import numpy as np
from scipy import signal

from djmcp.tools.dsp import load_audio, new_track_id, save_audio

FilterType = str  # "lowpass" | "highpass" | "bandpass"

_COMB_DELAYS_MS = (29.0, 37.0, 41.0, 43.0)
_COMB_FEEDBACK = 0.84
_ALLPASS_DELAYS_MS = (5.0, 1.7)
_ALLPASS_GAIN = 0.7


def _polyphase_iir(x: np.ndarray, delay_samples: int, b: list[float], a: list[float]) -> np.ndarray:
    """Apply an order-1 IIR independently to each of `delay_samples` interleaved
    phases of x -- the fast way to filter a single-tap feedback delay of D samples."""
    delay_samples = max(1, delay_samples)
    y = np.empty_like(x)
    for phase in range(delay_samples):
        y[phase::delay_samples] = signal.lfilter(b, a, x[phase::delay_samples])
    return y


def _comb_filter(x: np.ndarray, sr: int, delay_ms: float, feedback: float) -> np.ndarray:
    """y[n] = x[n] + feedback*y[n-D]."""
    delay_samples = int(sr * delay_ms / 1000)
    return _polyphase_iir(x, delay_samples, [1.0], [1.0, -feedback])


def _allpass_filter(x: np.ndarray, sr: int, delay_ms: float, gain: float) -> np.ndarray:
    """y[n] = -gain*x[n] + x[n-D] + gain*y[n-D]."""
    delay_samples = int(sr * delay_ms / 1000)
    return _polyphase_iir(x, delay_samples, [-gain, 1.0], [1.0, -gain])


def _sos_from_biquad(b0, b1, b2, a0, a1, a2) -> np.ndarray:
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


def _biquad_pass(kind: FilterType, f0: float, sr: float, q: float) -> np.ndarray:
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    cos_w0 = np.cos(w0)

    if kind == "lowpass":
        b0, b1, b2 = (1 - cos_w0) / 2, 1 - cos_w0, (1 - cos_w0) / 2
    elif kind == "highpass":
        b0, b1, b2 = (1 + cos_w0) / 2, -(1 + cos_w0), (1 + cos_w0) / 2
    elif kind == "bandpass":
        b0, b1, b2 = alpha, 0.0, -alpha
    else:
        raise ValueError(f"unknown filter type {kind!r}")

    a0, a1, a2 = 1 + alpha, -2 * cos_w0, 1 - alpha
    return _sos_from_biquad(b0, b1, b2, a0, a1, a2)


def _biquad_shelf(kind: str, f0: float, sr: float, gain_db: float, shelf_slope: float = 1.0) -> np.ndarray:
    a_gain = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    cos_w0, sin_w0 = np.cos(w0), np.sin(w0)
    alpha = sin_w0 / 2 * np.sqrt((a_gain + 1 / a_gain) * (1 / shelf_slope - 1) + 2)
    sqrt_a = np.sqrt(a_gain)

    if kind == "low_shelf":
        b0 = a_gain * ((a_gain + 1) - (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha)
        b1 = 2 * a_gain * ((a_gain - 1) - (a_gain + 1) * cos_w0)
        b2 = a_gain * ((a_gain + 1) - (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha)
        a0 = (a_gain + 1) + (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha
        a1 = -2 * ((a_gain - 1) + (a_gain + 1) * cos_w0)
        a2 = (a_gain + 1) + (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha
    elif kind == "high_shelf":
        b0 = a_gain * ((a_gain + 1) + (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha)
        b1 = -2 * a_gain * ((a_gain - 1) + (a_gain + 1) * cos_w0)
        b2 = a_gain * ((a_gain + 1) + (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha)
        a0 = (a_gain + 1) - (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha
        a1 = 2 * ((a_gain - 1) - (a_gain + 1) * cos_w0)
        a2 = (a_gain + 1) - (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha
    else:
        raise ValueError(f"unknown shelf kind {kind!r}")

    return _sos_from_biquad(b0, b1, b2, a0, a1, a2)


def _biquad_peaking(f0: float, sr: float, gain_db: float, q: float) -> np.ndarray:
    a_gain = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2 * q)
    cos_w0 = np.cos(w0)

    b0, b1, b2 = 1 + alpha * a_gain, -2 * cos_w0, 1 - alpha * a_gain
    a0, a1, a2 = 1 + alpha / a_gain, -2 * cos_w0, 1 - alpha / a_gain
    return _sos_from_biquad(b0, b1, b2, a0, a1, a2)


def apply_reverb(track_id: str, room_size: float = 0.5, wet: float = 0.3) -> dict:
    """Schroeder reverb: 4 parallel combs (delay scaled by room_size) -> 2 series allpasses."""
    y, sr = load_audio(track_id)
    room_size = float(np.clip(room_size, 0.0, 1.0))
    wet = float(np.clip(wet, 0.0, 1.0))

    diffuse = np.zeros_like(y)
    for base_delay_ms in _COMB_DELAYS_MS:
        delay_ms = base_delay_ms * (0.5 + room_size)
        diffuse += _comb_filter(y, sr, delay_ms, _COMB_FEEDBACK)
    diffuse /= len(_COMB_DELAYS_MS)

    for delay_ms in _ALLPASS_DELAYS_MS:
        diffuse = _allpass_filter(diffuse, sr, delay_ms, _ALLPASS_GAIN)

    mixed = (1 - wet) * y + wet * diffuse
    new_id = new_track_id(track_id, "reverb", room_size, wet)
    return save_audio(mixed, sr, new_id)


def apply_filter(track_id: str, type: FilterType, cutoff_hz: float, resonance: float = 0.7) -> dict:
    """2nd-order Butterworth-ish biquad (RBJ cookbook) with resonance mapped to Q."""
    if type not in ("lowpass", "highpass", "bandpass"):
        raise ValueError(f"type must be lowpass/highpass/bandpass, got {type!r}")

    y, sr = load_audio(track_id)
    cutoff_hz = float(np.clip(cutoff_hz, 20.0, sr / 2 - 100))
    q = 0.5 + max(0.0, resonance) * 9.5  # resonance in [0, 1] -> Q in [0.5, 10]

    sos = _biquad_pass(type, cutoff_hz, sr, q)
    filtered = signal.sosfilt(sos, y)
    new_id = new_track_id(track_id, f"filter-{type}", cutoff_hz, resonance)
    return save_audio(filtered, sr, new_id)


def apply_delay(track_id: str, time_ms: float = 250.0, feedback: float = 0.3, wet: float = 0.3) -> dict:
    """Feedback delay line (a single comb filter at a musically useful delay time)."""
    y, sr = load_audio(track_id)
    feedback = float(np.clip(feedback, 0.0, 0.95))
    wet = float(np.clip(wet, 0.0, 1.0))

    echoes = _comb_filter(y, sr, time_ms, feedback)
    mixed = (1 - wet) * y + wet * echoes
    new_id = new_track_id(track_id, "delay", time_ms, feedback, wet)
    return save_audio(mixed, sr, new_id)


def apply_eq(track_id: str, low_gain: float = 0.0, mid_gain: float = 0.0, high_gain: float = 0.0) -> dict:
    """3-band EQ: low-shelf @ 200Hz, peaking @ 1kHz, high-shelf @ 4kHz, in series."""
    y, sr = load_audio(track_id)

    if low_gain:
        y = signal.sosfilt(_biquad_shelf("low_shelf", 200.0, sr, low_gain), y)
    if mid_gain:
        y = signal.sosfilt(_biquad_peaking(1000.0, sr, mid_gain, q=1.0), y)
    if high_gain:
        y = signal.sosfilt(_biquad_shelf("high_shelf", 4000.0, sr, high_gain), y)

    new_id = new_track_id(track_id, "eq", low_gain, mid_gain, high_gain)
    return save_audio(y, sr, new_id)
