"""Detección local de la wake word "Jarvis".

Dos detectores complementarios, ambos 100% locales:

1. Acústico (``WakeWordDetector``): modelo ``hey_jarvis`` de openWakeWord. Instantáneo,
   pero entrenado con pronunciación inglesa: reconoce "Yárvis", no "Járbis".
2. Por transcripción (``match_wake_word``): el VAD recorta cada frase, Whisper la
   transcribe y se busca el nombre (o variantes como "Yarvis", "Harvis") entre
   las primeras palabras. Permite "Jarvis, ¿cómo estás?" de un tirón.

Se ejecuta la cadena de openWakeWord (Apache-2.0) directamente con onnxruntime:

    audio 16 kHz --(melspectrogram.onnx)--> mel (32 bandas, 10 ms)
                 --(embedding_model.onnx, ventana de 76 frames)--> embedding de 96
                 --(hey_jarvis_v0.1.onnx, últimos 16 embeddings)--> probabilidad

No se importa el paquete ``openwakeword`` porque su ``__init__`` carga scikit-learn,
cuyo ``_liblinear.pyd`` bloquea Smart App Control (ver docs/voice.md).
Todo el audio se procesa en local; nada sale del equipo.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import onnxruntime as ort

from app.core.logging import get_logger
from app.voice.models import ensure_wakeword_models

log = get_logger("voice.wakeword")

CHUNK_SAMPLES = 1280  # 80 ms a 16 kHz
MEL_CONTEXT = 480  # 3 hops extra para que cada bloque produzca 8 frames mel
MEL_WINDOW = 76  # frames por embedding
MEL_BUFFER_MAX = 970
FEATURE_BUFFER_MAX = 120
WARMUP_FRAMES = 5  # predicciones ignoradas tras un reset (como openWakeWord)


@dataclass(frozen=True)
class WakeEvent:
    word: str
    score: float
    source: str = "acoustic"  # "acoustic" (openWakeWord) o "transcript" (Whisper)
    command: str = ""  # lo dicho tras el nombre, si vino en la misma frase
    timestamp: float = field(default_factory=time.monotonic)


# Cómo suele transcribir Whisper "Jarvis" dicho en español.
DEFAULT_ALIASES = ("jarvis", "yarvis", "harvis", "jarbis", "yarbis", "harbis", "jarvi", "yarvi")


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def match_wake_word(
    text: str, aliases: tuple[str, ...] = DEFAULT_ALIASES, max_position: int = 4
) -> tuple[bool, str]:
    """Busca el nombre entre las primeras ``max_position`` palabras de una transcripción.

    Devuelve (encontrado, resto de la frase sin el nombre ni la puntuación inicial).
    """
    words = re.findall(r"\S+", text)
    folded_aliases = {_fold(alias) for alias in aliases}
    for index, word in enumerate(words[:max_position]):
        token = re.sub(r"[^\w]", "", _fold(word))
        if token in folded_aliases:
            remainder = " ".join(words[index + 1 :])
            return True, remainder.lstrip(" ,.;:!¡?¿-").strip()
    return False, ""


def _session(path: Path) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 3
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


class WakeWordDetector:
    def __init__(
        self,
        models_dir: Path,
        model_name: str = "hey_jarvis_v0.1",
        threshold: float = 0.5,
        patience: int = 1,
        word: str = "jarvis",
        download: bool = True,
    ) -> None:
        if download:
            ensure_wakeword_models(models_dir, model_name)
        folder = models_dir / "openwakeword"
        self._mel = _session(folder / "melspectrogram.onnx")
        self._embedding = _session(folder / "embedding_model.onnx")
        self._classifier = _session(folder / f"{model_name}.onnx")
        self._classifier_input = self._classifier.get_inputs()[0].name
        self._n_features = self._classifier.get_inputs()[0].shape[1]
        self.model_name = model_name
        self.word = word
        self.threshold = threshold
        self.patience = patience
        self._listeners: list[Callable[[WakeEvent], None]] = []
        self._baseline_features = self._embed(
            np.random.default_rng(0).integers(-1000, 1000, 16000 * 4).astype(np.float32)
        )
        self.reset()
        log.info("Wake word '%s' (%s) lista, umbral %.2f", word, model_name, threshold)

    # --- modelos -------------------------------------------------------------
    def _melspectrogram(self, audio: np.ndarray) -> np.ndarray:
        mel = self._mel.run(None, {"input": audio[None, :].astype(np.float32)})[0]
        return np.squeeze(mel, axis=(0, 1)) / 10.0 + 2.0  # transformación de openWakeWord

    def _embed(self, audio: np.ndarray) -> np.ndarray:
        mel = self._melspectrogram(audio)
        windows = [mel[i : i + MEL_WINDOW] for i in range(0, mel.shape[0] - MEL_WINDOW + 1, 8)]
        batch = np.stack(windows)[:, :, :, None].astype(np.float32)
        return self._embedding.run(None, {"input_1": batch})[0].reshape(-1, 96)

    # --- API -----------------------------------------------------------------
    def add_listener(self, callback: Callable[[WakeEvent], None]) -> None:
        self._listeners.append(callback)

    def reset(self) -> None:
        """Olvida el audio previo (p. ej. tras hablar JARVIS, para no reaccionar a su eco)."""
        self._tail = np.zeros(MEL_CONTEXT, dtype=np.float32)
        self._mel_buffer = np.ones((MEL_WINDOW, 32), dtype=np.float32)
        self._features = self._baseline_features.copy()
        self._frames = 0
        self._hits = 0
        self.last_score = 0.0

    def score(self, chunk: np.ndarray) -> float:
        """Procesa 1280 muestras int16 (80 ms) y devuelve la probabilidad de wake word."""
        samples = np.asarray(chunk).reshape(-1)
        if samples.size != CHUNK_SAMPLES:
            raise ValueError(f"se esperaban {CHUNK_SAMPLES} muestras, llegaron {samples.size}")
        audio = np.concatenate([self._tail, samples.astype(np.float32)])
        self._tail = audio[-MEL_CONTEXT:]

        mel = self._melspectrogram(audio)
        self._mel_buffer = np.vstack([self._mel_buffer, mel])[-MEL_BUFFER_MAX:]
        window = self._mel_buffer[-MEL_WINDOW:][None, :, :, None].astype(np.float32)
        embedding = self._embedding.run(None, {"input_1": window})[0].reshape(1, 96)
        self._features = np.vstack([self._features, embedding])[-FEATURE_BUFFER_MAX:]

        features = self._features[-self._n_features :][None].astype(np.float32)
        score = float(self._classifier.run(None, {self._classifier_input: features})[0][0][0])
        self._frames += 1
        if self._frames <= WARMUP_FRAMES:
            score = 0.0
        self.last_score = score
        return score

    def process(self, chunk: np.ndarray) -> WakeEvent | None:
        """Devuelve un WakeEvent (y avisa a los listeners) cuando se detecta la palabra."""
        score = self.score(chunk)
        self._hits = self._hits + 1 if score >= self.threshold else 0
        if self._hits < self.patience:
            return None
        event = WakeEvent(self.word, score, source="acoustic")
        log.info("Wake word detectada (score %.2f)", score)
        self.reset()
        for listener in self._listeners:
            listener(event)
        return event
