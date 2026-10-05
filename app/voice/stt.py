"""Voz a texto local con faster-whisper (CTranslate2), en GPU si está disponible."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.audio.analysis import to_float
from app.core.logging import get_logger
from app.voice.models import ensure_whisper_model

log = get_logger("voice.stt")

_dll_dirs_added = False


def add_cuda_dll_dirs() -> list[str]:
    """Registra las DLL de CUDA/cuDNN que instalan los wheels ``nvidia-*`` (solo Windows)."""
    global _dll_dirs_added
    if _dll_dirs_added or sys.platform != "win32":
        return []
    base = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    added = []
    for bin_dir in sorted(base.glob("*/bin")):
        os.add_dll_directory(str(bin_dir))
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
        added.append(str(bin_dir))
    _dll_dirs_added = True
    return added


def cuda_available() -> bool:
    add_cuda_dll_dirs()
    import ctranslate2

    return ctranslate2.get_cuda_device_count() > 0


# Frases que Whisper "inventa" con silencio o ruido (subtítulos de YouTube en su entrenamiento).
HALLUCINATIONS = {
    "gracias",
    "gracias por ver",
    "gracias por ver el video",
    "gracias por ver el vídeo",
    "subtitulos realizados por la comunidad de amara org",
    "subtítulos realizados por la comunidad de amara.org",
    "suscribete",
    "suscríbete al canal",
    "thank you",
    "thanks for watching",
}


def _normalize(text: str) -> str:
    return " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


_HALLUCINATIONS_NORMALIZED = {_normalize(h) for h in HALLUCINATIONS}


def is_hallucination(text: str) -> bool:
    normalized = _normalize(text)
    return not normalized or normalized in _HALLUCINATIONS_NORMALIZED


@dataclass
class Transcript:
    text: str
    language: str
    audio_seconds: float
    elapsed: float
    no_speech_prob: float = 0.0

    @property
    def is_empty(self) -> bool:
        return is_hallucination(self.text) or self.no_speech_prob > 0.8


class SpeechToText:
    def __init__(
        self,
        models_dir: Path,
        model: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "int8_float16",
        language: str = "es",
        beam_size: int = 1,
        prompt: str | None = None,
    ) -> None:
        from faster_whisper import WhisperModel

        if device == "auto":
            device = "cuda" if cuda_available() else "cpu"
        elif device == "cuda":
            add_cuda_dll_dirs()
        if device == "cpu" and "float16" in compute_type:
            compute_type = "int8"

        path = ensure_whisper_model(models_dir, model)
        start = time.perf_counter()
        self._model = WhisperModel(str(path), device=device, compute_type=compute_type)
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.beam_size = beam_size
        self.prompt = prompt or None
        log.info(
            "Whisper '%s' cargado en %s/%s en %.2f s",
            model,
            device,
            compute_type,
            time.perf_counter() - start,
        )

    def transcribe(self, audio: np.ndarray, initial_prompt: str | None = None) -> Transcript:
        """``audio``: mono a 16 kHz (int16 o float32)."""
        samples = to_float(np.asarray(audio).reshape(-1))
        start = time.perf_counter()
        segments, info = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,  # el VAD ya recortó la frase
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=initial_prompt if initial_prompt is not None else self.prompt,
        )
        segments = list(segments)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        no_speech = max((segment.no_speech_prob for segment in segments), default=1.0)
        return Transcript(
            text, info.language, len(samples) / 16000, time.perf_counter() - start, no_speech
        )

    def warmup(self) -> None:
        self.transcribe(np.zeros(16000, dtype=np.float32))
