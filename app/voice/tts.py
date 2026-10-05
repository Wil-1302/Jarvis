"""Texto a voz local con Piper (ONNX en CPU, sin servicios externos)."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.logging import get_logger
from app.voice.models import ensure_piper_voice, piper_voice_paths

log = get_logger("voice.tts")


@dataclass
class SpeechAudio:
    audio: np.ndarray  # int16 mono
    sample_rate: int
    synth_seconds: float

    @property
    def duration(self) -> float:
        return len(self.audio) / self.sample_rate


def clean_for_speech(text: str) -> str:
    """Quita marcas que Piper leería literalmente (markdown, emojis, listas)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"[*_`#>|~]", " ", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class TextToSpeech:
    def __init__(
        self,
        models_dir: Path,
        voice: str,
        length_scale: float = 1.0,
        download: bool = True,
    ) -> None:
        from piper import PiperVoice, SynthesisConfig

        model, config = piper_voice_paths(models_dir, voice)
        if download:
            ensure_piper_voice(models_dir, voice)
        start = time.perf_counter()
        self._voice = PiperVoice.load(model, config_path=config)
        self._syn_config = SynthesisConfig(length_scale=length_scale)
        self.voice_name = voice
        self.sample_rate = self._voice.config.sample_rate
        log.info(
            "Piper '%s' cargado en %.2f s (%d Hz)",
            voice,
            time.perf_counter() - start,
            self.sample_rate,
        )

    def synthesize_sentences(self, text: str) -> Iterator[SpeechAudio]:
        """Genera el audio frase a frase para empezar a hablar cuanto antes."""
        text = clean_for_speech(text)
        if not text:
            return
        start = time.perf_counter()
        for chunk in self._voice.synthesize(text, self._syn_config):
            elapsed = time.perf_counter() - start
            yield SpeechAudio(chunk.audio_int16_array, chunk.sample_rate, elapsed)
            start = time.perf_counter()

    def synthesize(self, text: str) -> SpeechAudio:
        start = time.perf_counter()
        parts = [part.audio for part in self.synthesize_sentences(text)]
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)
        return SpeechAudio(audio, self.sample_rate, time.perf_counter() - start)

    def warmup(self) -> None:
        self.synthesize("Hola.")
