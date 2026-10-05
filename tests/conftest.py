from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.brain.ollama_client import OllamaClient
from app.config.settings import Settings, load_settings
from app.core.logging import LOGGER_NAME

ENV_VARS = ("OLLAMA_HOST", "OLLAMA_MODEL", "CLAUDE_COMMAND")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla los tests de las variables JARVIS_* / OLLAMA_* reales del usuario."""
    import os

    for key in list(os.environ):
        if key.upper().startswith("JARVIS_") or key.upper() in ENV_VARS:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def reset_logger():
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def make_settings(tmp_path: Path) -> Callable[..., Settings]:
    """Crea Settings sin leer config/jarvis.toml ni .env, con workspace temporal."""

    def factory(**overrides) -> Settings:
        overrides.setdefault("workspace", tmp_path)
        overrides.setdefault("check_github", False)
        settings = load_settings(config_file=None, env_file=None)
        return settings.model_copy(update=overrides)

    return factory


@pytest.fixture
def settings(make_settings) -> Settings:
    return make_settings()


def fake_ollama_handler(
    models: list[str] | None = None, version: str = "0.0.test"
) -> Callable[[httpx.Request], httpx.Response]:
    models = ["qwen3:4b-instruct"] if models is None else models

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in models]})
        if request.url.path == "/api/chat":
            body = json.loads(request.content)
            content = '{"intent": "chat"}' if body.get("format") == "json" else "hola"
            return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})
        return httpx.Response(404, text="not found")

    return handler


def offline_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


@pytest.fixture(scope="session")
def voice_models_dir() -> Path:
    """Modelos reales en models/ (se descargan la primera vez)."""
    return load_settings(config_file=None, env_file=None).models_path


@pytest.fixture(scope="session")
def tts_engine(voice_models_dir):
    from app.voice.tts import TextToSpeech

    try:
        return TextToSpeech(voice_models_dir, "es_MX-claude-high")
    except Exception as exc:  # sin red ni modelo
        pytest.skip(f"Piper no disponible: {exc}")


@pytest.fixture(scope="session")
def spanish_speech(tts_engine):
    """'Jarvis, ¿cómo estás hoy?' sintetizado con Piper, int16 a 16 kHz."""
    from app.audio.resample import resample, to_int16

    speech = tts_engine.synthesize("Jarvis, ¿cómo estás hoy?")
    return to_int16(resample(speech.audio, speech.sample_rate, 16000))


@pytest.fixture
def fake_ollama() -> OllamaClient:
    return OllamaClient("http://ollama.test", transport=httpx.MockTransport(fake_ollama_handler()))


@pytest.fixture
def offline_ollama() -> OllamaClient:
    return OllamaClient("http://ollama.test", transport=httpx.MockTransport(offline_handler))
