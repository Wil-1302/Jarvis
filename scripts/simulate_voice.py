"""Conversación de voz simulada de punta a punta (sin hablar al micrófono).

    uv run python scripts/simulate_voice.py [--voice es_MX-claude-high] [--silent]

Genera las frases del usuario con Piper, las inyecta como si vinieran del micrófono
y ejecuta el pipeline real: wake word + VAD + Whisper + Ollama + Piper + altavoces.
Sirve para medir latencias reproducibles.
"""

from __future__ import annotations

import argparse
import sys
import threading

import numpy as np

from app.audio.resample import resample, to_int16
from app.cli import _print_voice_event
from app.config.settings import load_settings
from app.core.logging import setup_logging
from app.voice.pipeline import build_pipeline
from app.voice.simulation import SimulatedSource
from app.voice.tts import TextToSpeech

SCRIPT = ["Jarvis, ¿cómo estás?", "Jarvis.", "Dime hola.", "Jarvis, ¿qué es un agujero negro?"]


class SilentPlayer:
    def play(self, audio, samplerate, blocking=True) -> None:
        pass

    def wait(self) -> None:
        pass


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", default="es_MX-claude-high", help="voz del 'usuario'")
    parser.add_argument("--silent", action="store_true", help="no reproducir por altavoces")
    args = parser.parse_args()

    settings = load_settings()
    setup_logging(settings)
    user_voice = TextToSpeech(settings.models_path, args.voice)
    utterances = []
    for text in SCRIPT:
        speech = user_voice.synthesize(text)
        utterances.append(to_int16(resample(speech.audio, speech.sample_rate, 16000)))

    pipeline = build_pipeline(settings, on_event=_print_voice_event)
    pipeline.source = SimulatedSource(utterances, gap_s=1.0, realtime=True, noise_level=0.001)
    if args.silent:
        pipeline.player = SilentPlayer()
    print(f"Simulación: {SCRIPT}\n")
    stop = threading.Event()
    threading.Timer(90, stop.set).start()
    pipeline.run(stop, max_turns=3)
    stop.set()

    print("\n=== Resumen de latencias ===")
    for turn in pipeline.turns:
        print(f"- '{turn.transcript}' ({turn.wake_source}): {turn.summary()}")
    if pipeline.turns:
        first_audio = [t.first_audio_after_speech for t in pipeline.turns]
        print(f"Primer audio tras fin de voz: media {np.mean(first_audio):.2f}s, "
              f"máx {np.max(first_audio):.2f}s")
    return 0 if len(pipeline.turns) == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
