from __future__ import annotations

import numpy as np
import pytest

from app.voice.stt import Transcript, is_hallucination


@pytest.mark.parametrize(
    "text",
    ["", "  ", "Gracias.", "¡Gracias por ver el video!", "Suscríbete al canal", "Thank you."],
)
def test_hallucinations(text: str) -> None:
    assert is_hallucination(text)


@pytest.mark.parametrize("text", ["Gracias, Jarvis.", "Dime hola.", "¿Qué hora es?"])
def test_real_phrases_are_not_hallucinations(text: str) -> None:
    assert not is_hallucination(text)


def test_transcript_is_empty() -> None:
    assert Transcript("Gracias.", "es", 1.0, 0.1).is_empty
    assert Transcript("Hola", "es", 1.0, 0.1, no_speech_prob=0.95).is_empty
    assert not Transcript("Hola", "es", 1.0, 0.1, no_speech_prob=0.1).is_empty


@pytest.fixture(scope="module")
def stt(voice_models_dir):
    from app.voice.stt import SpeechToText

    try:
        return SpeechToText(voice_models_dir, "large-v3-turbo", prompt="Jarvis, Spotify.")
    except Exception as exc:
        pytest.skip(f"Whisper no disponible: {exc}")


@pytest.mark.integration
def test_transcribes_spanish(stt, spanish_speech) -> None:
    result = stt.transcribe(spanish_speech)
    assert "jarvis" in result.text.lower()
    assert "cómo estás" in result.text.lower()
    assert not result.is_empty


@pytest.mark.integration
def test_silence_is_empty(stt) -> None:
    assert stt.transcribe(np.zeros(32000, dtype=np.int16)).is_empty
