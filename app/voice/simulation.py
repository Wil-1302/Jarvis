"""Fuente de audio simulada para probar el pipeline sin micrófono.

Reproduce una lista de frases (audio int16 a 16 kHz) como lo haría un micrófono:
en bloques de 80 ms, opcionalmente al ritmo real, con silencio entre frases. Mientras
está silenciada (JARVIS hablando) descarta el audio, igual que ``MicrophoneStream``.
Cada frase empieza tras ``gap_s`` de silencio desde que el micrófono vuelve a escuchar.
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np

from app.audio.stream import FRAME_SAMPLES


class SimulatedSource:
    def __init__(
        self,
        utterances: list[np.ndarray],
        gap_s: float = 1.0,
        realtime: bool = False,
        noise_level: float = 0.0,
        seed: int = 0,
    ) -> None:
        self._utterances = deque(np.asarray(u, dtype=np.int16) for u in utterances)
        self._gap_chunks = max(1, round(gap_s * 16000 / FRAME_SAMPLES))
        self._realtime = realtime
        self._noise = noise_level
        self._rng = np.random.default_rng(seed)
        self._current: deque[np.ndarray] = deque()
        self._silence_left = self._gap_chunks
        self._muted = False
        self._next_time = time.perf_counter()
        self.finished = False

    def _silence(self) -> np.ndarray:
        if not self._noise:
            return np.zeros(FRAME_SAMPLES, dtype=np.int16)
        return (self._rng.normal(0, self._noise, FRAME_SAMPLES) * 32767).astype(np.int16)

    def _load_next(self) -> None:
        audio = self._utterances.popleft()
        padded = np.concatenate([audio, np.zeros(-audio.size % FRAME_SAMPLES, dtype=np.int16)])
        self._current = deque(padded.reshape(-1, FRAME_SAMPLES))

    def _next_chunk(self) -> np.ndarray:
        if self._current:
            return self._current.popleft()
        if self._silence_left > 0:
            self._silence_left -= 1
            return self._silence()
        if self._utterances:
            self._load_next()
            self._silence_left = self._gap_chunks
            return self._current.popleft()
        self.finished = True
        return self._silence()

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        if self._realtime:
            delay = self._next_time - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            self._next_time = max(self._next_time, time.perf_counter()) + FRAME_SAMPLES / 16000
        if self._muted:
            return None
        return self._next_chunk()

    def mute(self) -> None:
        self._muted = True

    def unmute(self) -> None:
        self._muted = False
        self._silence_left = self._gap_chunks
        self._next_time = time.perf_counter()

    def clear(self) -> int:
        return 0

    def __enter__(self) -> SimulatedSource:
        return self

    def __exit__(self, *exc: object) -> None:
        pass
