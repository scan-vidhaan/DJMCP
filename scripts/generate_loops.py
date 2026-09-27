"""One-off generator for the bundled drum/808 loop pack (djmcp/storage/loops/).

Run manually (`python scripts/generate_loops.py`) to (re)create the loop
files -- not called at runtime. Synthesized with numpy rather than sourced
externally so there's zero licensing question for files committed to the
repo: every loop here is code-generated, not a recording.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from pydub import AudioSegment

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import djmcp.config  # noqa: F401,E402 -- side effect: puts bundled ffmpeg on PATH

LOOPS_DIR = Path(__file__).resolve().parent.parent / "djmcp" / "storage" / "loops"
SR = 44100
BARS = 2
BEATS_PER_BAR = 4


def _kick(t: np.ndarray) -> np.ndarray:
    freq_env = 150 * np.exp(-40 * t) + 40
    phase = 2 * np.pi * np.cumsum(freq_env) / SR
    return np.sin(phase) * np.exp(-8 * t)


def _snare(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    noise = rng.uniform(-1, 1, len(t))
    tone = np.sin(2 * np.pi * 180 * t) * 0.4
    return (noise * 0.8 + tone) * np.exp(-25 * t)


def _hihat(t: np.ndarray, rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    noise = rng.uniform(-1, 1, len(t))
    decay = 6 if open_ else 35
    return noise * np.exp(-decay * t)


def _clap(t: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    # three quick noise bursts stacked to mimic a hand clap's flutter.
    out = np.zeros_like(t)
    for offset_ms in (0, 8, 16):
        shifted = np.clip(t - offset_ms / 1000, 0, None)
        out += rng.uniform(-1, 1, len(t)) * np.exp(-40 * shifted)
    return out / 3


def _sub808(t: np.ndarray, note_hz: float) -> np.ndarray:
    pitch_drop = note_hz * (1 + 0.5 * np.exp(-15 * t))
    phase = 2 * np.pi * np.cumsum(pitch_drop) / SR
    return np.sin(phase) * np.exp(-3 * t)


def _place(buffer: np.ndarray, sound: np.ndarray, start_sample: int) -> None:
    end = min(start_sample + len(sound), len(buffer))
    buffer[start_sample:end] += sound[: end - start_sample]


def _render_click_sound(kind: str, duration_sec: float, rng: np.random.Generator, **kwargs) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(SR * duration_sec), endpoint=False)
    if kind == "kick":
        return _kick(t)
    if kind == "snare":
        return _snare(t, rng)
    if kind == "hihat":
        return _hihat(t, rng, open_=kwargs.get("open_", False))
    if kind == "clap":
        return _clap(t, rng)
    if kind == "808":
        return _sub808(t, kwargs.get("note_hz", 55.0))
    raise ValueError(kind)


def _make_loop(bpm: float, pattern: dict[str, list[int]], seed: int) -> np.ndarray:
    """pattern maps sound kind -> list of 16th-note step indices (0-15 per bar) to trigger."""
    rng = np.random.default_rng(seed)
    beat_sec = 60.0 / bpm
    step_sec = beat_sec / 4  # 16th notes
    bar_samples = int(beat_sec * BEATS_PER_BAR * SR)
    total_samples = bar_samples * BARS
    buffer = np.zeros(total_samples)

    for kind, steps in pattern.items():
        for bar in range(BARS):
            for step in steps:
                start_sample = int((bar * BEATS_PER_BAR * beat_sec + step * step_sec) * SR)
                sound_kwargs = {"open_": kind == "ohat"}
                sound = _render_click_sound(kind.replace("ohat", "hihat"), 0.25, rng, **sound_kwargs)
                _place(buffer, sound, start_sample)

    peak = np.max(np.abs(buffer)) + 1e-9
    return buffer / peak * 0.85


LOOP_SPECS = [
    ("kick_four_on_floor_120", 120, {"kick": [0, 4, 8, 12]}),
    ("kick_snare_house_120", 120, {"kick": [0, 4, 8, 12], "snare": [4, 12]}),
    ("hihat_offbeat_120", 120, {"hihat": [2, 6, 10, 14]}),
    ("hihat_straight_16th_120", 120, {"hihat": list(range(16))}),
    ("clap_backbeat_120", 120, {"clap": [4, 12]}),
    ("808_pulse_120", 120, {"808": [0, 6, 8, 10]}),
    ("full_groove_house_124", 124, {"kick": [0, 4, 8, 12], "snare": [4, 12], "hihat": [2, 6, 10, 14]}),
    ("kick_trap_140", 140, {"kick": [0, 7, 8]}),
    ("ohat_trap_140", 140, {"ohat": [3, 11]}),
    ("hihat_trap_roll_140", 140, {"hihat": [0, 2, 4, 5, 6, 8, 10, 12, 13, 14]}),
    ("808_trap_140", 140, {"808": [0, 8]}),
    ("clap_trap_140", 140, {"clap": [8]}),
    ("kick_snare_dnb_174", 174, {"kick": [0, 10], "snare": [4, 12]}),
    ("hihat_dnb_174", 174, {"hihat": [0, 2, 4, 6, 8, 10, 12, 14]}),
    ("full_groove_dnb_174", 174, {"kick": [0, 10], "snare": [4, 12], "hihat": [2, 6, 10, 14]}),
]


def main() -> None:
    LOOPS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    for name, bpm, pattern in LOOP_SPECS:
        audio = _make_loop(bpm, pattern, seed=hash(name) % (2**32))
        wav_path = LOOPS_DIR / f"{name}.wav"
        mp3_path = LOOPS_DIR / f"{name}.mp3"

        audio_int16 = (audio * 32767).astype(np.int16)
        sf.write(str(wav_path), audio_int16, SR, subtype="PCM_16")
        AudioSegment.from_wav(str(wav_path)).export(str(mp3_path), format="mp3", bitrate="192k")
        wav_path.unlink()

        manifest.append({"name": name, "bpm": bpm, "bars": BARS, "file": mp3_path.name})
        print(f"generated {mp3_path.name} @ {bpm} BPM")

    (LOOPS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(manifest)} loops written to {LOOPS_DIR}")


if __name__ == "__main__":
    main()
