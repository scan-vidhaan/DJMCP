"""Quality checks on finished mixes."""

from __future__ import annotations

import numpy as np

from djmcp.tools.dsp import load_audio

WINDOW_SEC = 0.5
SILENCE_DB = -60.0


def check_seams(track_id: str, threshold_db: float = 9.0) -> dict:
    """Find abrupt level jumps: a sudden cut, a clipped entry, a bad join.

    Compares loudness of consecutive 0.5 s windows; a change above
    threshold_db between two non-silent windows is flagged. Gradual
    crossfades change by well under that per window.
    """
    y, sr = load_audio(track_id)
    win = int(WINDOW_SEC * sr)
    if len(y) < 2 * win:
        return {"track_id": track_id, "passed": True, "jumps": [], "threshold_db": threshold_db}

    n = len(y) // win
    rms = np.sqrt(np.mean(y[: n * win].reshape(n, win) ** 2, axis=1)) + 1e-12
    db = 20 * np.log10(rms)

    jumps = []
    for i in range(1, n):
        if db[i] < SILENCE_DB and db[i - 1] < SILENCE_DB:
            continue
        delta = float(db[i] - db[i - 1])
        if abs(delta) > threshold_db:
            jumps.append({"time_sec": round(i * WINDOW_SEC, 2), "delta_db": round(delta, 1)})
    return {"track_id": track_id, "passed": not jumps, "jumps": jumps, "threshold_db": threshold_db}
