from __future__ import annotations

import json

import httpx
import pytest

from app.brain.conversation import ConversationBrain, split_sentences
from app.brain.ollama_client import OllamaClient, OllamaError


def test_split_sentences_from_stream() -> None:
    pieces = ["Hola", ", estoy ", "bien. ¿Y", " tú? Todo ", "listo"]
    # "¿Y tú?" es demasiado corta para hablarla sola: se une a la siguiente.
    assert list(split_sentences(iter(pieces))) == ["Hola, estoy bien.", "¿Y tú? Todo listo"]


def test_split_sentences_keeps_spaces_across_pieces() -> None:
    pieces = ["Esto es una frase larga. Y", " otra ", "frase ", "que sigue."]
    assert list(split_sentences(iter(pieces))) == [
        "Esto es una frase larga.",
        "Y otra frase que sigue.",
    ]


def test_split_sentences_merges_very_short_ones() -> None:
    assert list(split_sentences(iter(["Sí. Claro. Lo haré ahora mismo."]))) == [
        "Sí. Claro. Lo haré ahora mismo."
    ]


def _streaming_handler(chunks: list[str], seen: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        lines = [json.dumps({"message": {"content": c}, "done": False}) for c in chunks]
        lines.append(json.dumps({"message": {"content": ""}, "done": True}))
        return httpx.Response(200, content="\n".join(lines).encode())

    return handler


def test_stream_chat_yields_pieces() -> None:
    seen: dict = {}
    client = OllamaClient(
        "http://ollama.test", transport=httpx.MockTransport(_streaming_handler(["Ho", "la"], seen))
    )
    assert list(client.stream_chat("m", [], keep_alive="5m", max_tokens=10)) == ["Ho", "la"]
    assert seen["stream"] is True
    assert seen["keep_alive"] == "5m"
    assert seen["options"]["num_predict"] == 10


def test_stream_chat_error_line() -> None:
    def handler(request):
        return httpx.Response(200, content=json.dumps({"error": "model not found"}).encode())

    client = OllamaClient("http://ollama.test", transport=httpx.MockTransport(handler))
    with pytest.raises(OllamaError, match="model not found"):
        list(client.stream_chat("m", []))


def test_brain_keeps_history_and_system_prompt() -> None:
    seen: dict = {}
    client = OllamaClient(
        "http://ollama.test",
        transport=httpx.MockTransport(_streaming_handler(["Estoy bien, gracias."], seen)),
    )
    brain = ConversationBrain(client, "qwen3:4b-instruct", name="Jarvis", max_words=40)
    assert brain.reply("¿Cómo estás?") == "Estoy bien, gracias."
    system = seen["messages"][0]
    assert system["role"] == "system"
    assert "Jarvis" in system["content"] and "40 palabras" in system["content"]

    brain.reply("Dime hola.")
    roles = [m["role"] for m in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert len(brain.history) == 4


def test_brain_history_is_bounded() -> None:
    seen: dict = {}
    client = OllamaClient(
        "http://ollama.test", transport=httpx.MockTransport(_streaming_handler(["Ok."], seen))
    )
    brain = ConversationBrain(client, "m", history_turns=2)
    for i in range(5):
        brain.reply(f"pregunta {i}")
    assert len(seen["messages"]) == 1 + 2 * 2 + 1


@pytest.mark.integration
def test_real_brain_answers_in_spanish() -> None:
    from app.config.settings import load_settings

    settings = load_settings(env_file=None)
    client = OllamaClient(settings.ollama_host, timeout=120)
    try:
        client.version()
    except OllamaError:
        pytest.skip("Ollama no está en ejecución")
    brain = ConversationBrain(client, settings.ollama_model, max_words=30)
    reply = brain.reply("Dime hola en una frase corta.")
    assert "hola" in reply.lower()
    assert "*" not in reply
