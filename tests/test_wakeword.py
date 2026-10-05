from __future__ import annotations

import numpy as np
import pytest

from app.voice.wakeword import CHUNK_SAMPLES, WakeWordDetector, match_wake_word


@pytest.mark.parametrize(
    ("text", "found", "rest"),
    [
        ("Jarvis, ¿cómo estás?", True, "cómo estás?"),
        ("Jarvis.", True, ""),
        ("Oye Jarvis abre Spotify", True, "abre Spotify"),
        ("Yarvis, dime hola", True, "dime hola"),
        ("JARBIS: pon música", True, "pon música"),
        ("Hoy hace buen día.", False, ""),
        ("Le dije a mi amigo que Jarvis es genial", False, ""),  # demasiado lejos del inicio
        ("Javier, ven aquí", False, ""),
    ],
)
def test_match_wake_word(text: str, found: bool, rest: str) -> None:
    assert match_wake_word(text) == (found, rest)


def test_match_wake_word_custom_aliases() -> None:
    assert match_wake_word("Friday, hola", aliases=("friday",)) == (True, "hola")


@pytest.fixture(scope="module")
def detector(voice_models_dir):
    try:
        return WakeWordDetector(voice_models_dir)
    except Exception as exc:
        pytest.skip(f"modelos de openWakeWord no disponibles: {exc}")


def test_detector_quiet_on_silence(detector) -> None:
    detector.reset()
    scores = [detector.score(np.zeros(CHUNK_SAMPLES, dtype=np.int16)) for _ in range(30)]
    assert max(scores) < 0.1


def test_detector_rejects_wrong_chunk_size(detector) -> None:
    with pytest.raises(ValueError):
        detector.score(np.zeros(1000, dtype=np.int16))


def test_detector_warmup_frames_are_zero(detector) -> None:
    detector.reset()
    noise = np.random.default_rng(0).integers(-3000, 3000, CHUNK_SAMPLES).astype(np.int16)
    assert [detector.score(noise) for _ in range(5)] == [0.0] * 5


def test_detector_notifies_listeners(detector, monkeypatch) -> None:
    events = []
    detector.add_listener(events.append)
    monkeypatch.setattr(detector, "score", lambda chunk: 0.97)
    event = detector.process(np.zeros(CHUNK_SAMPLES, dtype=np.int16))
    assert event is not None and event.source == "acoustic"
    assert events == [event]
    detector._listeners.clear()


def test_detector_patience(voice_models_dir, monkeypatch) -> None:
    detector = WakeWordDetector(voice_models_dir, patience=3)
    monkeypatch.setattr(detector, "score", lambda chunk: 0.9)
    chunk = np.zeros(CHUNK_SAMPLES, dtype=np.int16)
    assert detector.process(chunk) is None
    assert detector.process(chunk) is None
    assert detector.process(chunk) is not None


@pytest.mark.integration
def test_detector_detects_english_hey_jarvis(detector, voice_models_dir) -> None:
    """El modelo hey_jarvis reconoce la pronunciación inglesa (voz Piper en_US)."""
    from app.audio.resample import resample, to_int16
    from app.voice.tts import TextToSpeech

    try:
        english = TextToSpeech(voice_models_dir, "en_US-lessac-medium")
    except Exception as exc:
        pytest.skip(f"voz inglesa no disponible: {exc}")

    def max_score(text: str) -> float:
        speech = english.synthesize(text)
        audio = to_int16(resample(speech.audio, speech.sample_rate, 16000))
        audio = np.concatenate([np.zeros(16000, np.int16), audio, np.zeros(16000, np.int16)])
        audio = audio[: audio.size - audio.size % CHUNK_SAMPLES]
        detector.reset()
        return max(detector.score(c) for c in audio.reshape(-1, CHUNK_SAMPLES))

    assert max_score("Hey Jarvis.") > 0.9
    assert max_score("Hello, how are you?") < 0.1
