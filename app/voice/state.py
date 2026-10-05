"""Máquina de estados del asistente de voz.

    IDLE -> WAKE_DETECTED -> LISTENING -> TRANSCRIBING -> THINKING -> SPEAKING -> IDLE

Atajos permitidos:
- IDLE -> TRANSCRIBING: en modo híbrido cada frase se transcribe para buscar "Jarvis".
- TRANSCRIBING -> WAKE_DETECTED: la frase solo contenía el nombre.
- TRANSCRIBING -> THINKING: el nombre y la orden llegaron juntos.
- LISTENING/TRANSCRIBING/THINKING -> IDLE: silencio, nada entendido o error.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.logging import get_logger

log = get_logger("voice.state")


class VoiceState(StrEnum):
    IDLE = "IDLE"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


TRANSITIONS: dict[VoiceState, frozenset[VoiceState]] = {
    VoiceState.IDLE: frozenset({VoiceState.WAKE_DETECTED, VoiceState.TRANSCRIBING}),
    VoiceState.WAKE_DETECTED: frozenset({VoiceState.LISTENING, VoiceState.SPEAKING}),
    VoiceState.LISTENING: frozenset({VoiceState.TRANSCRIBING, VoiceState.IDLE}),
    VoiceState.TRANSCRIBING: frozenset(
        {VoiceState.THINKING, VoiceState.WAKE_DETECTED, VoiceState.IDLE}
    ),
    VoiceState.THINKING: frozenset({VoiceState.SPEAKING, VoiceState.IDLE}),
    VoiceState.SPEAKING: frozenset({VoiceState.IDLE, VoiceState.LISTENING}),
}


class InvalidTransition(Exception):
    pass


@dataclass(frozen=True)
class Transition:
    previous: VoiceState
    current: VoiceState
    reason: str
    at: float  # time.perf_counter()
    elapsed_in_previous: float


class StateMachine:
    def __init__(self, initial: VoiceState = VoiceState.IDLE) -> None:
        self._state = initial
        self._entered_at = time.perf_counter()
        self._lock = threading.Lock()
        self._listeners: list[Callable[[Transition], None]] = []
        self.history: list[Transition] = []

    @property
    def state(self) -> VoiceState:
        return self._state

    def can_transition(self, target: VoiceState) -> bool:
        return target in TRANSITIONS[self._state]

    def add_listener(self, callback: Callable[[Transition], None]) -> None:
        self._listeners.append(callback)

    def transition(self, target: VoiceState, reason: str = "") -> Transition:
        with self._lock:
            if not self.can_transition(target):
                raise InvalidTransition(f"{self._state} -> {target} no permitido ({reason})")
            now = time.perf_counter()
            event = Transition(self._state, target, reason, now, now - self._entered_at)
            self._state, self._entered_at = target, now
            self.history.append(event)
            if len(self.history) > 200:
                del self.history[:100]
        log.debug("%s -> %s (%s)", event.previous, event.current, reason)
        for listener in self._listeners:
            listener(event)
        return event

    def reset(self, reason: str = "reset") -> None:
        """Vuelve a IDLE desde cualquier estado (errores o cancelación)."""
        if self._state is not VoiceState.IDLE:
            with self._lock:
                now = time.perf_counter()
                event = Transition(self._state, VoiceState.IDLE, reason, now, now - self._entered_at)
                self._state, self._entered_at = VoiceState.IDLE, now
                self.history.append(event)
            for listener in self._listeners:
                listener(event)
