from __future__ import annotations

import numpy as np
import pytest

from app.voice.tts import clean_for_speech


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("**Hola**, soy _Jarvis_.", "Hola , soy Jarvis ."),
        ("- uno\n- dos", "uno dos"),
        ("Listo 😊👍", "Listo"),
        ("Mira:\n```python\nprint(1)\n```\nya está", "Mira: ya está"),
        ("   ", ""),
    ],
)
def test_clean_for_speech(raw: str, clean: str) -> None:
    assert clean_for_speech(raw) == clean


@pytest.mark.integration
def test_piper_synthesizes_spanish(tts_engine) -> None:
    speech = tts_engine.synthesize("Hola, soy Jarvis. El sistema de voz está funcionando.")
    assert speech.audio.dtype == np.int16
    assert speech.sample_rate == tts_engine.sample_rate
    assert 2.0 < speech.duration < 8.0
    assert np.abs(speech.audio).max() > 1000


@pytest.mark.integration
def test_piper_yields_one_chunk_per_sentence(tts_engine) -> None:
    parts = list(tts_engine.synthesize_sentences("Primera frase. Segunda frase."))
    assert len(parts) == 2


@pytest.mark.integration
def test_empty_text_produces_no_audio(tts_engine) -> None:
    assert tts_engine.synthesize("**").audio.size == 0
