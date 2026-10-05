"""Captura continua del micrófono y reproducción por los altavoces."""

from __future__ import annotations

import queue
import threading

import numpy as np
import sounddevice as sd

from app.audio.device_manager import AudioDevice
from app.core.logging import get_logger

log = get_logger("audio.stream")

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280  # 80 ms: el tamaño que procesa el modelo de wake word


class MicrophoneStream:
    """Entrega frames int16 mono de ``FRAME_SAMPLES`` muestras a 16 kHz.

    El callback de PortAudio solo copia el audio a una cola; todo el procesado
    ocurre en el hilo consumidor para no perder frames.
    """

    def __init__(
        self,
        device: AudioDevice | None = None,
        samplerate: int = SAMPLE_RATE,
        frame_samples: int = FRAME_SAMPLES,
        max_queue_frames: int = 250,  # ~20 s
    ) -> None:
        self.device = device
        self.samplerate = samplerate
        self.frame_samples = frame_samples
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_frames)
        self._stream: sd.InputStream | None = None
        self._muted = threading.Event()
        self.overflows = 0
        self.dropped = 0

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:  # noqa: ANN001
        if status.input_overflow:
            self.overflows += 1
        if self._muted.is_set():
            return
        try:
            self._queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            self.dropped += 1

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            device=self.device.index if self.device else None,
            samplerate=self.samplerate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_samples,
            callback=self._callback,
        )
        self._stream.start()
        log.info(
            "Micrófono abierto: %s @ %d Hz",
            self.device.name if self.device else "predeterminado",
            self.samplerate,
        )

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("Micrófono cerrado")

    def read(self, timeout: float | None = None) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear(self) -> int:
        """Descarta el audio pendiente (p. ej. el eco de JARVIS hablando)."""
        cleared = 0
        while True:
            try:
                self._queue.get_nowait()
                cleared += 1
            except queue.Empty:
                return cleared

    def mute(self) -> None:
        self._muted.set()

    def unmute(self) -> None:
        self._muted.clear()

    @property
    def muted(self) -> bool:
        return self._muted.is_set()

    def __enter__(self) -> MicrophoneStream:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


class AudioPlayer:
    def __init__(self, device: AudioDevice | None = None) -> None:
        self.device = device

    def play(self, audio: np.ndarray, samplerate: int, blocking: bool = True) -> None:
        sd.play(audio, samplerate, device=self.device.index if self.device else None)
        if blocking:
            sd.wait()

    def wait(self) -> None:
        sd.wait()

    def stop(self) -> None:
        sd.stop()


def record(seconds: float, device: AudioDevice | None, samplerate: int = SAMPLE_RATE) -> np.ndarray:
    audio = sd.rec(
        int(seconds * samplerate),
        samplerate=samplerate,
        channels=1,
        dtype="int16",
        device=device.index if device else None,
    )
    sd.wait()
    return audio[:, 0]
