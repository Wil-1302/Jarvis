from __future__ import annotations

import pytest

from app.voice.state import InvalidTransition, StateMachine, VoiceState


def test_full_cycle() -> None:
    machine = StateMachine()
    for target in (
        VoiceState.WAKE_DETECTED,
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.THINKING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ):
        machine.transition(target)
    assert machine.state is VoiceState.IDLE
    assert len(machine.history) == 6


def test_invalid_transition_raises() -> None:
    machine = StateMachine()
    with pytest.raises(InvalidTransition):
        machine.transition(VoiceState.SPEAKING)
    assert machine.state is VoiceState.IDLE


def test_listeners_receive_transitions() -> None:
    machine = StateMachine()
    seen = []
    machine.add_listener(seen.append)
    machine.transition(VoiceState.TRANSCRIBING, "frase")
    assert seen[0].previous is VoiceState.IDLE
    assert seen[0].current is VoiceState.TRANSCRIBING
    assert seen[0].reason == "frase"
    assert seen[0].elapsed_in_previous >= 0


def test_reset_from_any_state() -> None:
    machine = StateMachine()
    machine.transition(VoiceState.TRANSCRIBING)
    machine.transition(VoiceState.THINKING)
    machine.reset("error")
    assert machine.state is VoiceState.IDLE
    assert machine.history[-1].reason == "error"


def test_reset_when_idle_is_noop() -> None:
    machine = StateMachine()
    machine.reset()
    assert machine.history == []


def test_can_transition() -> None:
    machine = StateMachine()
    assert machine.can_transition(VoiceState.WAKE_DETECTED)
    assert not machine.can_transition(VoiceState.THINKING)
