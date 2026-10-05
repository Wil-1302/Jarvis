from __future__ import annotations

import json

import httpx
import pytest

from app.brain.ollama_client import OllamaClient, OllamaError
from app.config.settings import load_settings
from tests.conftest import fake_ollama_handler


def test_version_and_models(fake_ollama: OllamaClient) -> None:
    assert fake_ollama.version() == "0.0.test"
    assert fake_ollama.list_models() == ["qwen3:4b-instruct"]


def test_has_model_handles_latest_tag() -> None:
    client = OllamaClient(
        "http://ollama.test",
        transport=httpx.MockTransport(fake_ollama_handler(models=["llama3.2:latest"])),
    )
    assert client.has_model("llama3.2")
    assert client.has_model("llama3.2:latest")
    assert not client.has_model("qwen3:4b-instruct")


def test_chat_sends_expected_payload() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "{}"}})

    client = OllamaClient("http://ollama.test", transport=httpx.MockTransport(handler))
    client.chat("m", [{"role": "user", "content": "hola"}], json_format=True)
    assert seen["model"] == "m"
    assert seen["stream"] is False
    assert seen["format"] == "json"
    assert seen["options"]["temperature"] == 0.0


def test_connection_error_raises_ollama_error(offline_ollama: OllamaClient) -> None:
    with pytest.raises(OllamaError, match="No se pudo conectar"):
        offline_ollama.version()


def test_http_error_raises_ollama_error() -> None:
    client = OllamaClient(
        "http://ollama.test",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    )
    with pytest.raises(OllamaError, match="HTTP 500"):
        client.list_models()


@pytest.fixture
def real_ollama():
    settings = load_settings(env_file=None)
    client = OllamaClient(settings.ollama_host, timeout=120)
    try:
        client.version()
    except OllamaError:
        client.close()
        pytest.skip("Ollama no está en ejecución")
    yield client, settings
    client.close()


@pytest.mark.integration
def test_real_ollama_connection(real_ollama) -> None:
    client, settings = real_ollama
    assert client.version()
    assert client.has_model(settings.ollama_model), f"falta {settings.ollama_model}"


@pytest.mark.integration
def test_real_model_classifies_intent(real_ollama) -> None:
    client, settings = real_ollama
    reply = client.chat(
        settings.ollama_model,
        [
            {
                "role": "system",
                "content": 'Responde SOLO JSON: {"intent": "open_app" | "chat", "app": string}',
            },
            {"role": "user", "content": "Jarvis, abre la calculadora"},
        ],
        json_format=True,
    )
    data = json.loads(reply)
    assert data["intent"] == "open_app"
