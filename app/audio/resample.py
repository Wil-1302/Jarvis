"""Remuestreo sencillo (interpolación lineal), suficiente para voz hacia 16 kHz."""

from __future__ import annotations

import numpy as np


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Devuelve float32; acepta int16 o float."""
    from app.audio.analysis import to_float

    samples = to_float(np.asarray(audio).reshape(-1))
    if src_rate == dst_rate or samples.size == 0:
        return samples
    duration = samples.size / src_rate
    n_out = int(round(duration * dst_rate))
    src_t = np.arange(samples.size) / src_rate
    dst_t = np.arange(n_out) / dst_rate
    return np.interp(dst_t, src_t, samples).astype(np.float32)


def to_int16(audio: np.ndarray) -> np.ndarray:
    return (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
