"""Detección de actividad de voz (Silero VAD v6 en ONNX) y segmentación de frases.

``SileroVAD`` da la probabilidad de voz cada 32 ms. ``SpeechSegmenter`` la usa
para decidir cuándo empieza y cuándo termina una frase (SILENCE -> VOICE -> SILENCE).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import onnxruntime as ort

from app.audio.analysis import to_float
from app.core.logging import get_logger
from app.voice.models import silero_vad_path

log = get_logger("voice.vad")

SAMPLE_RATE = 16000
VAD_FRAME = 512  # 32 ms
VAD_CONTEXT = 64


class SileroVAD:
    def __init__(self, model_path: Path | None = None) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(
            str(model_path or silero_vad_path()), options, providers=["CPUExecutionProvider"]
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(VAD_CONTEXT, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)

    def frame_probability(self, frame: np.ndarray) -> float:
        """Probabilidad de voz para exactamente 512 muestras float32."""
        batch = np.concatenate([self._context, frame])[None, :].astype(np.float32)
        prob, self._h, self._c = self._session.run(
            None, {"input": batch, "h": self._h, "c": self._c}
        )
        self._context = frame[-VAD_CONTEXT:]
        return float(np.asarray(prob).reshape(-1)[0])

    def process(self, chunk: np.ndarray) -> list[float]:
        """Acepta bloques de cualquier tamaño; devuelve una probabilidad por cada 32 ms completo."""
        self._pending = np.concatenate([self._pending, to_float(np.asarray(chunk).reshape(-1))])
        probs = []
        while self._pending.size >= VAD_FRAME:
            frame, self._pending = self._pending[:VAD_FRAME], self._pending[VAD_FRAME:]
            probs.append(self.frame_probability(frame))
        return probs


class VadState(StrEnum):
    SILENCE = "SILENCE"
    VOICE = "VOICE"


class SegmentKind(StrEnum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"  # frase completa en ``audio``
    TIMEOUT = "timeout"  # no empezó a hablar a tiempo


@dataclass
class SegmentEvent:
    kind: SegmentKind
    audio: np.ndarray | None = None  # int16, 16 kHz

    @property
    def duration(self) -> float:
        return 0.0 if self.audio is None else self.audio.size / SAMPLE_RATE


class SpeechSegmenter:
    """Recorta frases a partir de bloques de audio int16.

    - Empieza la voz cuando la probabilidad supera ``threshold``.
    - Termina cuando cae por debajo de ``threshold - 0.15`` durante ``min_silence_ms``.
    - Se añade ``speech_pad_ms`` de audio previo para no cortar la primera sílaba.
    - Las frases más cortas que ``min_speech_ms`` se descartan (clics, golpes).
    """

    def __init__(
        self,
        vad: SileroVAD,
        threshold: float = 0.5,
        min_silence_ms: int = 700,
        speech_pad_ms: int = 200,
        min_speech_ms: int = 250,
        max_utterance_s: float = 15.0,
        start_timeout_s: float | None = None,
    ) -> None:
        self.vad = vad
        self.threshold = threshold
        self.end_threshold = max(threshold - 0.15, 0.01)
        frame_ms = VAD_FRAME * 1000 / SAMPLE_RATE
        self._silence_frames_needed = max(1, round(min_silence_ms / frame_ms))
        self._min_speech_frames = max(1, round(min_speech_ms / frame_ms))
        self._max_samples = int(max_utterance_s * SAMPLE_RATE)
        self._pad_samples = int(speech_pad_ms * SAMPLE_RATE / 1000)
        self.start_timeout_s = start_timeout_s
        self.reset()

    def reset(self, start_timeout_s: float | None = None) -> None:
        self.vad.reset()
        if start_timeout_s is not None:
            self.start_timeout_s = start_timeout_s
        self.state = VadState.SILENCE
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_samples = 0
        self._speech: list[np.ndarray] = []
        self._speech_samples = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._waited_samples = 0
        self.last_probability = 0.0

    def arm_timeout(self, start_timeout_s: float | None) -> None:
        """Activa el tiempo máximo de espera sin perder la frase que pueda estar en curso."""
        self.start_timeout_s = start_timeout_s
        self._waited_samples = 0

    def _push_preroll(self, chunk: np.ndarray) -> None:
        self._preroll.append(chunk)
        self._preroll_samples += chunk.size
        while self._preroll and self._preroll_samples - self._preroll[0].size >= self._pad_samples:
            self._preroll_samples -= self._preroll.popleft().size

    def _finish(self) -> SegmentEvent | None:
        audio = np.concatenate(self._speech) if self._speech else np.zeros(0, dtype=np.int16)
        long_enough = self._speech_frames >= self._min_speech_frames
        self.reset(self.start_timeout_s)
        if not long_enough:
            return None
        return SegmentEvent(SegmentKind.SPEECH_END, audio)

    def feed(self, chunk: np.ndarray) -> SegmentEvent | None:
        chunk = np.asarray(chunk, dtype=np.int16).reshape(-1)
        probs = self.vad.process(chunk)
        if probs:
            self.last_probability = max(probs)

        if self.state is VadState.SILENCE:
            if any(p >= self.threshold for p in probs):
                self.state = VadState.VOICE
                self._speech = [*self._preroll, chunk]
                self._speech_samples = sum(c.size for c in self._speech)
                self._speech_frames = sum(p >= self.threshold for p in probs)
                self._silence_frames = 0
                self._preroll.clear()
                self._preroll_samples = 0
                return SegmentEvent(SegmentKind.SPEECH_START)
            self._push_preroll(chunk)
            self._waited_samples += chunk.size
            if (
                self.start_timeout_s is not None
                and self._waited_samples >= self.start_timeout_s * SAMPLE_RATE
            ):
                self.reset(self.start_timeout_s)
                return SegmentEvent(SegmentKind.TIMEOUT)
            return None

        # VOICE
        self._speech.append(chunk)
        self._speech_samples += chunk.size
        for p in probs:
            if p >= self.end_threshold:
                self._speech_frames += p >= self.threshold
                self._silence_frames = 0
            else:
                self._silence_frames += 1
        if self._silence_frames >= self._silence_frames_needed:
            return self._finish()
        if self._speech_samples >= self._max_samples:
            log.info("Frase cortada al alcanzar el máximo de %.0f s", self._max_samples / 16000)
            return self._finish()
        return None
