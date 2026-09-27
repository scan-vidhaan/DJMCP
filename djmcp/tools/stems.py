"""Stem separation via demucs -- vocal_boost (boosters.py) and mashup (mix.py).

Imported lazily by callers: demucs pulls in PyTorch, the one genuinely
heavy dependency in this project (installed via the optional [boosters]
extra), so importing this module eagerly would slow every tool import even
when stem separation is never used.
"""

from __future__ import annotations

import numpy as np
import torch
from demucs.api import Separator

from djmcp.tools.common import resolve_track_path
from djmcp.tools.dsp import new_track_id, save_audio

STEM_NAMES = ("vocals", "drums", "bass", "other")

_separator: Separator | None = None


def _get_separator() -> Separator:
    global _separator
    if _separator is None:
        _separator = Separator(model="htdemucs", device="cpu", progress=False)
    return _separator


def _to_mono_numpy(wave: torch.Tensor) -> np.ndarray:
    """demucs returns (channels, samples) tensors; the rest of this project
    processes mono throughout, so downmix here rather than threading stereo
    through every effect."""
    return wave.mean(dim=0).cpu().numpy()


def separate(track_id: str) -> dict[str, torch.Tensor]:
    """Split a track into {"vocals", "drums", "bass", "other"} stem tensors."""
    audio_path = resolve_track_path(track_id)
    if audio_path is None:
        raise FileNotFoundError(f"no track found for track_id={track_id!r}")

    separator = _get_separator()
    _original, stems = separator.separate_audio_file(audio_path)
    return stems


def boost_stem(track_id: str, stem_name: str, gain_db: float) -> dict:
    """Separate, boost one stem's gain, remix, export."""
    if stem_name not in STEM_NAMES:
        raise ValueError(f"stem_name must be one of {STEM_NAMES}, got {stem_name!r}")

    stems = separate(track_id)
    stems[stem_name] = stems[stem_name] * (10 ** (gain_db / 20))

    remixed = sum(stems.values())
    y = _to_mono_numpy(remixed)
    sr = _get_separator().samplerate

    new_id = new_track_id(track_id, f"boost-{stem_name}", gain_db)
    return save_audio(y, sr, new_id)
