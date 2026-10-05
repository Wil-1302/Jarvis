"""Conversación por voz con el modelo local (Ollama).

En la Fase 2 JARVIS solo conversa: todavía no ejecuta acciones en el equipo.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from app.brain.ollama_client import OllamaClient
from app.core.logging import get_logger

log = get_logger("brain.conversation")

SYSTEM_PROMPT = """Eres {name}, un asistente personal de voz que funciona en la computadora del usuario.
Hablas español latino neutro, con un tono cordial, seguro y un toque de humor elegante.
Tus respuestas se leerán en voz alta, así que:
- Responde en 1 a 3 frases cortas, con un máximo de {max_words} palabras.
- No uses markdown, listas, emojis, código ni URLs.
- Escribe los números como se dicen cuando sea natural.
Todavía no puedes ejecutar acciones en la computadora (abrir aplicaciones, poner música,
buscar en internet ni leer archivos). Si te lo piden, dilo con naturalidad y añade que
esa capacidad llegará pronto. Nunca finjas haber realizado una acción."""

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_sentences(stream: Iterator[str], min_chars: int = 12) -> Iterator[str]:
    """Agrupa fragmentos de texto en frases completas para poder hablar mientras se generan."""
    buffer = ""
    for piece in stream:
        buffer += piece
        parts = _SENTENCE_END.split(buffer)
        # Todas menos la última están completas.
        complete, buffer = parts[:-1], parts[-1]
        pending = ""
        for sentence in complete:
            pending = f"{pending} {sentence}".strip()
            if len(pending) >= min_chars:
                yield pending
                pending = ""
        if pending:
            # Sin strip: el final de ``buffer`` puede ser un espacio entre palabras a medias.
            buffer = f"{pending} {buffer}"
    if buffer.strip():
        yield buffer.strip()


class ConversationBrain:
    def __init__(
        self,
        client: OllamaClient,
        model: str,
        name: str = "Jarvis",
        max_words: int = 60,
        history_turns: int = 6,
        keep_alive: str = "30m",
    ) -> None:
        self.client = client
        self.model = model
        self.keep_alive = keep_alive
        self.history_turns = history_turns
        self._system = SYSTEM_PROMPT.format(name=name, max_words=max_words)
        self._max_tokens = max_words * 3
        self.history: list[dict[str, str]] = []

    def warmup(self) -> None:
        self.client.load(self.model, self.keep_alive)

    def _messages(self, text: str) -> list[dict[str, str]]:
        recent = self.history[-self.history_turns * 2 :]
        return [
            {"role": "system", "content": self._system},
            *recent,
            {"role": "user", "content": text},
        ]

    def reply_sentences(self, text: str) -> Iterator[str]:
        """Genera la respuesta frase a frase y la guarda en el historial al terminar."""
        stream = self.client.stream_chat(
            self.model,
            self._messages(text),
            keep_alive=self.keep_alive,
            max_tokens=self._max_tokens,
        )
        said: list[str] = []
        for sentence in split_sentences(stream):
            said.append(sentence)
            yield sentence
        reply = " ".join(said)
        self.history += [
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ]
        log.info("Respuesta generada (%d caracteres)", len(reply))

    def reply(self, text: str) -> str:
        return " ".join(self.reply_sentences(text))
