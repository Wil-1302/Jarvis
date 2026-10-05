"""Diagnóstico de audio.

    python -m app.audio --devices
    python -m app.audio --record-test [--seconds 5] [--no-playback]
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from app.audio.analysis import analyze
from app.audio.device_manager import (
    AudioDeviceError,
    find_device,
    list_devices,
    supported_samplerates,
)
from app.audio.stream import SAMPLE_RATE, AudioPlayer, record
from app.config.settings import load_settings
from app.core.logging import setup_logging


def print_devices(host_api: str) -> None:
    for kind, title in (("input", "INPUT DEVICES"), ("output", "OUTPUT DEVICES")):
        print(title)
        for device in list_devices(kind, host_api):
            mark = " (default)" if device.is_default_input or device.is_default_output else ""
            print(
                f"[{device.index}] {device.name}{mark}"
                f"  | {device.channels(kind)} ch, {device.default_samplerate:.0f} Hz"
            )
        print()

    for kind, label in (("input", "Default microphone"), ("output", "Default speakers")):
        try:
            device = find_device(kind, "", host_api)
        except AudioDeviceError as exc:
            print(f"{label}: no disponible ({exc})")
            continue
        rates = supported_samplerates(device, kind)
        print(
            f"{label}: [{device.index}] {device.name} | {device.channels(kind)} ch | "
            f"sample rates: {', '.join(map(str, rates)) or 'ninguno'}"
        )
    print(f"Host API: {host_api}")


def _write_wav(path: Path, audio: np.ndarray, samplerate: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(samplerate)
        wav.writeframes(audio.astype(np.int16).tobytes())


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16), wav.getframerate()


def record_test(input_selector: str, output_selector: str, host_api: str, seconds: float,
                playback: bool) -> int:
    mic = find_device("input", input_selector, host_api)
    speakers = find_device("output", output_selector, host_api)
    print(f"Grabando {seconds:.0f} s desde '{mic.name}'... habla ahora.")
    audio = record(seconds, mic, SAMPLE_RATE)

    fd, name = tempfile.mkstemp(prefix="jarvis-mic-test-", suffix=".wav")
    os.close(fd)
    path = Path(name)
    try:
        _write_wav(path, audio, SAMPLE_RATE)
        loaded, rate = _read_wav(path)
        report = analyze(loaded, rate)
        print()
        print(f"Microphone: {mic.name}")
        print(f"Sample rate: {rate}")
        print("Channels: 1")
        print(f"RMS: {report.rms:.4f} ({report.rms_dbfs:.1f} dBFS)")
        print(f"Peak: {report.peak:.4f} ({report.peak_dbfs:.1f} dBFS)")
        print(f"Noise floor: {report.noise_floor:.4f} ({report.noise_dbfs:.1f} dBFS)")
        print(f"Clipping: {'YES (' + str(report.clipped_samples) + ' muestras)' if report.clipping else 'NO'}")
        print(f"Signal detected: {'YES' if report.signal_detected else 'NO'}")
        if playback:
            print(f"\nReproduciendo por '{speakers.name}'...")
            AudioPlayer(speakers).play(loaded, rate)
    finally:
        path.unlink(missing_ok=True)
    print(f"Archivo temporal eliminado: {not path.exists()}")
    return 0 if report.signal_detected else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="python -m app.audio")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--devices", action="store_true", help="lista los dispositivos de audio")
    group.add_argument("--record-test", action="store_true", help="graba, analiza y reproduce")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--no-playback", action="store_true")
    parser.add_argument("--host-api", default=None, help="MME, Windows WASAPI, ...")
    args = parser.parse_args(argv)

    settings = load_settings()
    setup_logging(settings)
    host_api = args.host_api or settings.audio_host_api
    try:
        if args.devices:
            print_devices(host_api)
            return 0
        return record_test(
            settings.audio_input_device,
            settings.audio_output_device,
            host_api,
            args.seconds,
            playback=not args.no_playback,
        )
    except AudioDeviceError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
