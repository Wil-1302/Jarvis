"""VAD Silero en streaming + segmentador de frases.

Usa el ONNX de Silero que ya trae faster-whisper (sin dependencias nuevas), en CPU con 1 hilo.
Ventanas de 512 muestras (32 ms a 16 kHz) con 64 de contexto y estado LSTM persistente.

Segmentador: una frase empieza tras `start_frames` ventanas con voz y termina tras `end_silence`
segundos sin voz (0,7 s por defecto). Incluye `preroll` de audio previo para no cortar la primera sílaba.
"""
from __future__ import annotations

import collections
import os
import time

import numpy as np

FRAME = 512
CONTEXT = 64
RATE = 16000


class SileroVAD:
    def __init__(self):
        import onnxruntime
        from faster_whisper.utils import get_assets_path
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self.session = onnxruntime.InferenceSession(
            os.path.join(get_assets_path(), "silero_vad_v6.onnx"),
            providers=["CPUExecutionProvider"], sess_options=opts)
        self.reset()

    def reset(self) -> None:
        self.h = np.zeros((1, 1, 128), np.float32)
        self.c = np.zeros((1, 1, 128), np.float32)
        self.ctx = np.zeros(CONTEXT, np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        """frame: 512 muestras float32 en [-1, 1]. Devuelve la probabilidad de voz."""
        x = np.concatenate([self.ctx, frame])[None, :]
        out, self.h, self.c = self.session.run(None, {"input": x, "h": self.h, "c": self.c})
        self.ctx = frame[-CONTEXT:]
        return float(out.ravel()[0])


class Utterance:
    __slots__ = ("audio", "t_start", "t_end", "t_emit")

    def __init__(self, audio, t_start, t_end, t_emit):
        self.audio, self.t_start, self.t_end, self.t_emit = audio, t_start, t_end, t_emit

    @property
    def seconds(self) -> float:
        return len(self.audio) / RATE


class Segmenter:
    """Recibe audio int16/float32 de cualquier tamaño y devuelve las frases terminadas."""

    def __init__(self, threshold=0.5, end_silence=0.7, min_speech=0.25, max_seconds=20.0,
                 preroll=0.3, start_frames=3):
        self.vad = SileroVAD()
        self.th, self.th_off = threshold, threshold - 0.15
        self.end_frames = int(end_silence * RATE / FRAME)
        self.min_frames = int(min_speech * RATE / FRAME)
        self.max_frames = int(max_seconds * RATE / FRAME)
        self.start_frames = start_frames
        self.pre = collections.deque(maxlen=int(preroll * RATE / FRAME))
        self._buf = np.zeros(0, np.float32)
        self.reset()

    def reset(self) -> None:
        self.vad.reset()
        self.active = False
        self.frames: list[np.ndarray] = []
        self.voiced = 0
        self.run = 0          # ventanas con voz seguidas (para arrancar)
        self.silence = 0      # ventanas sin voz seguidas (para cortar)
        self.t_start = 0.0
        self.t_last_voice = 0.0
        self.pre.clear()
        self.last_prob = 0.0

    @property
    def in_speech(self) -> bool:
        return self.active

    def feed(self, pcm: np.ndarray, now: float | None = None) -> list[Utterance]:
        if pcm.dtype == np.int16:
            pcm = pcm.astype(np.float32) / 32768
        now = time.time() if now is None else now
        self._buf = np.concatenate([self._buf, pcm])
        n = len(self._buf) // FRAME
        out: list[Utterance] = []
        for i in range(n):
            fr = self._buf[i * FRAME:(i + 1) * FRAME]
            t = now - (n - 1 - i) * FRAME / RATE  # instante aproximado del final de esta ventana
            p = self.last_prob = self.vad(fr)
            if not self.active:
                self.pre.append(fr)
                self.run = self.run + 1 if p >= self.th else 0
                if self.run >= self.start_frames:
                    self.active = True
                    self.frames = list(self.pre)
                    self.voiced, self.silence = self.run, 0
                    self.t_start = t - len(self.frames) * FRAME / RATE
                    self.t_last_voice = t
                continue
            self.frames.append(fr)
            if p >= self.th_off:
                self.voiced += 1
                self.silence = 0
                self.t_last_voice = t
            else:
                self.silence += 1
            if self.silence >= self.end_frames or len(self.frames) >= self.max_frames:
                if self.voiced >= self.min_frames:
                    keep = len(self.frames) - max(0, self.silence - 6)  # deja ~0,2 s de cola
                    out.append(Utterance(np.concatenate(self.frames[:keep]), self.t_start, self.t_last_voice, t))
                self.active = False
                self.frames, self.run, self.silence, self.voiced = [], 0, 0, 0
                self.pre.clear()
        self._buf = self._buf[n * FRAME:]
        return out
