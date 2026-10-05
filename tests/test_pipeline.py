from __future__ import annotations

import threading

import numpy as np
import pytest

from app.voice.pipeline import ACK_TEXT, ERROR_TEXT, VoicePipeline
from app.voice.simulation import SimulatedSource
from app.voice.state import VoiceState
from app.voice.vad import SpeechSegmenter
from tests.voice_fakes import (
    FakeBrain,
    FakePlayer,
    FakeSTT,
    FakeTTS,
    FakeVAD,
    FakeWake,
    tone,
)

TEXTS = {
    1000: "Jarvis, ¿cómo estás?",
    2000: "Jarvis.",
    3000: "Dime hola.",
    4000: "Hoy hace buen día.",
    5000: "Gracias por ver el video.",
}


def make_pipeline(utterances, brain=None, wake=None, engine="transcript", listen_timeout_s=6.0):
    """``utterances``: pares (amplitud, segundos) o arrays de audio ya construidos."""
    audio = [u if isinstance(u, np.ndarray) else tone(*u) for u in utterances]
    source = SimulatedSource(audio, gap_s=0.5)
    stt = FakeSTT(TEXTS)
    tts = FakeTTS()
    player = FakePlayer(source)
    events = []
    pipeline = VoicePipeline(
        source=source,
        segmenter=SpeechSegmenter(FakeVAD(), min_silence_ms=300, min_speech_ms=100),
        stt=stt,
        brain=brain or FakeBrain(),
        tts=tts,
        player=player,
        wake=wake,
        engine=engine,
        listen_timeout_s=listen_timeout_s,
        echo_cooldown_ms=0,
        on_event=events.append,
    )
    return pipeline, source, stt, tts, player, events


def run_until(pipeline, source, turns=None, max_chunks=2000):
    for _ in range(max_chunks):
        chunk = source.read()
        if chunk is not None:
            pipeline.process_chunk(chunk)
        if turns is not None and len(pipeline.turns) >= turns:
            return
        if source.finished and pipeline.state.state is VoiceState.IDLE and turns is None:
            return


def test_one_shot_command_with_wake_word() -> None:
    brain = FakeBrain("Estoy muy bien. Gracias por preguntar.")
    pipeline, source, _, tts, player, _ = make_pipeline([(1000, 1.0)], brain=brain)
    run_until(pipeline, source, turns=1)

    assert brain.prompts == ["cómo estás?"]
    assert tts.spoken == ["Estoy muy bien", "Gracias por preguntar."]
    assert player.played == 2
    assert all(player.muted_while_playing), "el micrófono debe estar silenciado al hablar"
    assert not source._muted
    assert pipeline.state.state is VoiceState.IDLE
    metrics = pipeline.turns[0]
    assert metrics.wake_source == "transcript"
    assert metrics.first_audio_after_speech > 0


def test_wake_word_then_command() -> None:
    pipeline, source, stt, tts, _, _ = make_pipeline([(2000, 0.6), (3000, 1.0)])
    run_until(pipeline, source, turns=1)
    assert tts.spoken[0] == ACK_TEXT
    assert pipeline.brain.prompts == ["Dime hola."]
    states = [t.current for t in pipeline.state.history]
    assert VoiceState.WAKE_DETECTED in states
    assert VoiceState.LISTENING in states


def test_speech_without_wake_word_is_ignored() -> None:
    pipeline, source, _, tts, _, events = make_pipeline([(4000, 1.0)])
    run_until(pipeline, source)
    assert pipeline.brain.prompts == []
    assert tts.spoken == []
    assert any(e.kind == "ignored" and e.data["reason"] == "sin wake word" for e in events)


def test_hallucinations_are_ignored() -> None:
    pipeline, source, _, tts, _, _ = make_pipeline([(5000, 1.0)])
    run_until(pipeline, source)
    assert tts.spoken == []
    assert pipeline.state.state is VoiceState.IDLE


def test_timeout_after_wake_returns_to_idle() -> None:
    pipeline, source, _, tts, _, events = make_pipeline([(2000, 0.6)], listen_timeout_s=1.0)
    run_until(pipeline, source, max_chunks=200)
    assert tts.spoken == [ACK_TEXT]
    assert pipeline.brain.prompts == []
    assert pipeline.state.state is VoiceState.IDLE
    assert any(e.kind == "ignored" and "no se detectó voz" in e.data["reason"] for e in events)


def test_acoustic_wake_captures_following_command() -> None:
    wake = FakeWake(trigger_amplitude=7000)
    # "Jarvis" (acústico) y la orden en una sola frase continua, como al hablar seguido.
    spoken = np.concatenate([tone(7000, 0.16), tone(3000, 1.0)])
    pipeline, source, _, _, _, events = make_pipeline([spoken], wake=wake, engine="hybrid")
    run_until(pipeline, source, turns=1)
    assert any(e.kind == "wake" and e.data["source"] == "acoustic" for e in events)
    assert pipeline.turns[0].wake_source == "acoustic"
    assert wake.resets >= 1


def test_brain_error_is_spoken() -> None:
    pipeline, source, _, tts, _, events = make_pipeline([(1000, 1.0)], brain=FakeBrain(fail=True))
    run_until(pipeline, source, turns=1)
    assert ERROR_TEXT in tts.spoken
    assert any(e.kind == "error" for e in events)
    assert pipeline.state.state is VoiceState.IDLE


def test_no_echo_loop_after_speaking() -> None:
    """Lo que 'oye' el micrófono mientras JARVIS habla nunca dispara otro turno."""
    brain = FakeBrain("Jarvis aquí. Jarvis responde.")
    pipeline, source, stt, _, _, _ = make_pipeline([(1000, 1.0)], brain=brain)
    run_until(pipeline, source, max_chunks=400)
    assert len(pipeline.turns) == 1
    assert len(stt.calls) == 1


def test_acoustic_engine_requires_detector() -> None:
    with pytest.raises(ValueError):
        make_pipeline([], engine="acoustic")


def test_run_stops_with_event() -> None:
    pipeline, *_ = make_pipeline([(4000, 0.5)])
    stop = threading.Event()
    stop.set()
    pipeline.run(stop)
    assert pipeline.turns == []
