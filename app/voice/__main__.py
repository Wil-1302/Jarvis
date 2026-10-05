"""Pruebas de los componentes de voz.

    python -m app.voice --download-models
    python -m app.voice --wake-test [--seconds 60]
    python -m app.voice --vad-test [--seconds 20]
    python -m app.voice --stt-test
    python -m app.voice --tts-test [--text "..."]
"""

from __future__ import annotations

import argparse
import sys
import time

from app.config.settings import Settings, load_settings
from app.core.logging import setup_logging

TTS_TEST_TEXT = "Hola, soy Jarvis. El sistema de voz está funcionando correctamente."


def _mic(settings: Settings):
    from app.audio.device_manager import find_device
    from app.audio.stream import MicrophoneStream

    device = find_device("input", settings.audio_input_device, settings.audio_host_api)
    print(f"Micrófono: {device.name}")
    return MicrophoneStream(device)


def _segmenter(settings: Settings, timeout: float | None = None):
    from app.voice.vad import SileroVAD, SpeechSegmenter

    return SpeechSegmenter(
        SileroVAD(),
        threshold=settings.vad_threshold,
        min_silence_ms=settings.vad_min_silence_ms,
        speech_pad_ms=settings.vad_speech_pad_ms,
        max_utterance_s=settings.max_utterance_s,
        start_timeout_s=timeout,
    )


def _stt(settings: Settings):
    from app.voice.stt import SpeechToText

    print(f"Cargando Whisper '{settings.stt_model}'...")
    stt = SpeechToText(
        settings.models_path,
        settings.stt_model,
        settings.stt_device,
        settings.stt_compute_type,
        settings.language,
        settings.stt_beam_size,
        settings.stt_prompt,
    )
    stt.warmup()
    print(f"Whisper listo en {stt.device} ({stt.compute_type}).")
    return stt


def download_models(settings: Settings) -> int:
    from app.voice import models

    print("Descargando modelos en", settings.models_path)
    models.ensure_wakeword_models(settings.models_path, settings.wake_model)
    models.ensure_piper_voice(settings.models_path, settings.tts_voice)
    models.ensure_whisper_model(settings.models_path, settings.stt_model)
    print("Silero VAD:", models.silero_vad_path())
    print("Listo.")
    return 0


def wake_test(settings: Settings, seconds: float) -> int:
    from app.voice.wakeword import WakeWordDetector, match_wake_word

    engine = settings.wake_engine
    detector = None
    if engine in ("hybrid", "acoustic"):
        detector = WakeWordDetector(
            settings.models_path,
            settings.wake_model,
            settings.wake_threshold,
            settings.wake_patience,
            word=settings.wake_word,
        )
    stt = _stt(settings) if engine in ("hybrid", "transcript") else None
    segmenter = _segmenter(settings)
    detections = 0
    microphone = _mic(settings)

    print(f"\nListening for wake word: {settings.wake_word.capitalize()}  (modo {engine})")
    print("Waiting...  (Ctrl+C para salir)\n")
    deadline = time.monotonic() + seconds
    with microphone as mic:
        try:
            while time.monotonic() < deadline:
                chunk = mic.read(timeout=0.5)
                if chunk is None:
                    continue
                if detector is not None:
                    event = detector.process(chunk)
                    if event is not None:
                        detections += 1
                        print(f"[detected] {event.word.capitalize()}  (acústico, score {event.score:.2f})")
                if stt is None:
                    continue
                segment = segmenter.feed(chunk)
                if segment is not None and segment.audio is not None and segment.duration <= 10:
                    result = stt.transcribe(segment.audio)
                    found, rest = match_wake_word(result.text, tuple(settings.wake_aliases))
                    if found and not result.is_empty:
                        detections += 1
                        extra = f" -> orden: \"{rest}\"" if rest else ""
                        print(f"[detected] Jarvis  (transcripción: \"{result.text}\"){extra}")
                    elif not result.is_empty:
                        print(f"  (oído sin wake word: \"{result.text}\")")
        except KeyboardInterrupt:
            pass
    print(f"\nDetecciones: {detections}")
    return 0


def vad_test(settings: Settings, seconds: float) -> int:
    from app.voice.vad import SegmentKind

    segmenter = _segmenter(settings)
    microphone = _mic(settings)
    print("Habla y haz pausas; se mostrarán los cambios SILENCE / VOICE.\n")
    print("SILENCE")
    deadline = time.monotonic() + seconds
    with microphone as mic:
        try:
            while time.monotonic() < deadline:
                chunk = mic.read(timeout=0.5)
                if chunk is None:
                    continue
                event = segmenter.feed(chunk)
                if event is None:
                    continue
                if event.kind is SegmentKind.SPEECH_START:
                    print("VOICE")
                elif event.kind is SegmentKind.SPEECH_END:
                    print(f"SILENCE  (frase de {event.duration:.2f} s)")
        except KeyboardInterrupt:
            pass
    return 0


def stt_test(settings: Settings, timeout: float) -> int:
    from app.voice.vad import SegmentKind

    stt = _stt(settings)
    segmenter = _segmenter(settings, timeout=timeout)
    microphone = _mic(settings)
    print(f"\nHabla ahora (tienes {timeout:.0f} s para empezar)...")
    with microphone as mic:
        while True:
            chunk = mic.read(timeout=0.5)
            if chunk is None:
                continue
            event = segmenter.feed(chunk)
            if event is None:
                continue
            if event.kind is SegmentKind.SPEECH_START:
                print("(escuchando...)")
            elif event.kind is SegmentKind.TIMEOUT:
                print("No se detectó voz.")
                return 1
            elif event.kind is SegmentKind.SPEECH_END:
                break
    result = stt.transcribe(event.audio)
    print("\nYou said:")
    print(f"\"{result.text}\"")
    print(f"\n({event.duration:.2f} s de audio transcritos en {result.elapsed:.2f} s)")
    return 0 if not result.is_empty else 1


def tts_test(settings: Settings, text: str) -> int:
    from app.audio.device_manager import find_device
    from app.audio.stream import AudioPlayer
    from app.voice.tts import TextToSpeech

    tts = TextToSpeech(settings.models_path, settings.tts_voice, settings.tts_length_scale)
    speech = tts.synthesize(text)
    device = find_device("output", settings.audio_output_device, settings.audio_host_api)
    print(f"Voz: {settings.tts_voice} | Altavoces: {device.name}")
    print(f"\"{text}\"")
    print(f"({speech.duration:.2f} s de audio sintetizados en {speech.synth_seconds:.2f} s)")
    AudioPlayer(device).play(speech.audio, speech.sample_rate)
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m app.voice")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--download-models", action="store_true")
    group.add_argument("--wake-test", action="store_true")
    group.add_argument("--vad-test", action="store_true")
    group.add_argument("--stt-test", action="store_true")
    group.add_argument("--tts-test", action="store_true")
    parser.add_argument("--seconds", type=float, default=60.0, help="duración de wake/vad test")
    parser.add_argument("--timeout", type=float, default=8.0, help="espera máxima del stt-test")
    parser.add_argument("--text", default=TTS_TEST_TEXT, help="texto del tts-test")
    args = parser.parse_args(argv)

    settings = load_settings()
    setup_logging(settings)
    if args.download_models:
        return download_models(settings)
    if args.wake_test:
        return wake_test(settings, args.seconds)
    if args.vad_test:
        return vad_test(settings, args.seconds)
    if args.stt_test:
        return stt_test(settings, args.timeout)
    return tts_test(settings, args.text)


if __name__ == "__main__":
    raise SystemExit(main())
