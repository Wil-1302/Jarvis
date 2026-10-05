"""Dobles de prueba para el pipeline de voz (sin micrófono, GPU ni Ollama)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.brain.ollama_client import OllamaError
from app.voice.stt import Transcript
from app.voice.tts import SpeechAudio
from app.voice.wakeword import WakeEvent


def tone(amplitude: int, seconds: float = 1.0) -> np.ndarray:
    """Audio int16 constante: la amplitud identifica cada 'frase' en los fakes."""
    return np.full(int(16000 * seconds), amplitude, dtype=np.int16)


class FakeVAD:
    """Voz = cualquier frame con energía; una probabilidad por cada 512 muestras."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._pending = 0

    def process(self, chunk: np.ndarray) -> list[float]:
        prob = 1.0 if np.abs(chunk).mean() > 50 else 0.0
        self._pending += chunk.size
        n, self._pending = divmod(self._pending, 512)
        return [prob] * n


class FakeSTT:
    """Devuelve el texto asociado a la amplitud del audio recibido."""

    def __init__(self, texts: dict[int, str]) -> None:
        self.texts = texts
        self.calls: list[str] = []

    def transcribe(self, audio: np.ndarray) -> Transcript:
        values = np.abs(audio[audio != 0])
        key = int(np.median(values)) if values.size else 0
        text = self.texts.get(key, "")
        self.calls.append(text)
        return Transcript(text, "es", audio.size / 16000, 0.01, 0.0 if text else 1.0)


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize_sentences(self, text: str):
        self.spoken.append(text)
        yield SpeechAudio(np.zeros(160, dtype=np.int16), 16000, 0.001)


class FakePlayer:
    def __init__(self, source=None) -> None:
        self.played = 0
        self.source = source
        self.muted_while_playing: list[bool] = []

    def play(self, audio, samplerate, blocking=True) -> None:
        self.played += 1
        if self.source is not None:
            self.muted_while_playing.append(self.source._muted)

    def wait(self) -> None:
        pass


class FakeBrain:
    def __init__(self, reply: str = "Hola. Estoy bien.", fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.prompts: list[str] = []

    def reply_sentences(self, text: str):
        self.prompts.append(text)
        if self.fail:
            raise OllamaError("Ollama apagado")
        yield from self.reply.split(". ")


@dataclass
class FakeWake:
    """Se activa con la amplitud indicada."""

    trigger_amplitude: int
    resets: int = 0

    def process(self, chunk: np.ndarray) -> WakeEvent | None:
        if int(np.abs(chunk).max()) == self.trigger_amplitude:
            return WakeEvent("jarvis", 0.99)
        return None

    def reset(self) -> None:
        self.resets += 1
