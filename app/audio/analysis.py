"""Métricas de nivel de audio: RMS, pico, ruido de fondo, clipping y detección de señal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CLIP_LEVEL = 0.999  # fracción del fondo de escala
SIGNAL_MIN_PEAK_DBFS = -45.0
SIGNAL_MIN_DYNAMIC_DB = 10.0  # diferencia entre las partes más fuertes y el ruido de fondo


def to_float(audio: np.ndarray) -> np.ndarray:
    """int16 -> float32 en [-1, 1]; float se devuelve como float32."""
    if audio.dtype == np.int16:
        return audio.astype(np.float32) / 32768.0
    return audio.astype(np.float32, copy=False)


def dbfs(value: float) -> float:
    return float(20 * np.log10(max(value, 1e-10)))


@dataclass(frozen=True)
class LevelReport:
    rms: float
    peak: float
    noise_floor: float
    loud_level: float
    clipped_samples: int

    @property
    def rms_dbfs(self) -> float:
        return dbfs(self.rms)

    @property
    def peak_dbfs(self) -> float:
        return dbfs(self.peak)

    @property
    def noise_dbfs(self) -> float:
        return dbfs(self.noise_floor)

    @property
    def clipping(self) -> bool:
        return self.clipped_samples > 0

    @property
    def signal_detected(self) -> bool:
        dynamic = dbfs(self.loud_level) - self.noise_dbfs
        return self.peak_dbfs > SIGNAL_MIN_PEAK_DBFS and dynamic > SIGNAL_MIN_DYNAMIC_DB


def analyze(audio: np.ndarray, samplerate: int, frame_ms: int = 30) -> LevelReport:
    """Analiza audio mono (int16 o float). El ruido es el percentil 10 del RMS por frame."""
    samples = to_float(np.asarray(audio).reshape(-1))
    if samples.size == 0:
        return LevelReport(0.0, 0.0, 0.0, 0.0, 0)
    frame = max(1, samplerate * frame_ms // 1000)
    usable = samples[: samples.size - samples.size % frame] if samples.size >= frame else samples
    frames = usable.reshape(-1, min(frame, usable.size))
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))
    return LevelReport(
        rms=float(np.sqrt(np.mean(samples**2))),
        peak=float(np.max(np.abs(samples))),
        noise_floor=float(np.percentile(frame_rms, 10)),
        loud_level=float(np.percentile(frame_rms, 95)),
        clipped_samples=int(np.count_nonzero(np.abs(samples) >= CLIP_LEVEL)),
    )
