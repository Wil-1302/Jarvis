"""Micrófono compartido: UN solo stream de captura por PipeWire para la wake word y la grabación.

Se usa `pw-record` (cliente nativo de PipeWire) en vez de PortAudio/ALSA:
- Apunta a un nodo concreto (`audio.mic_target`, el micrófono del portátil). Si ese nodo no existe,
  WirePlumber lo enlaza a la fuente por defecto. Nunca abrimos el micrófono Bluetooth a propósito:
  abrirlo pasaría los audífonos a HSP/HFP (mono, 16 kHz) y la música sonaría distorsionada.
- Pide 16 kHz mono s16: PipeWire remuestrea en el propio stream; la frecuencia del grafo (48 kHz) no cambia.
- Latencia de nodo de 80 ms (igual que el bloque de openWakeWord): no fuerza al grafo a un quantum bajo.

Los consumidores se suscriben y reciben bloques de 1280 muestras (80 ms) en una cola propia.
El hub también estima el ruido de fondo (percentil 20 del RMS de los últimos ~10 s) para que la
detección de voz/silencio del STT se adapte a la sala.
"""
from __future__ import annotations

import collections
import os
import queue
import subprocess
import threading
import time

import numpy as np

RATE = 16000
BLOCK = 1280  # 80 ms; lo que espera openWakeWord
_BYTES = BLOCK * 2


class MicHub:
    def __init__(self, target: str | None = None):
        self.target = target
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._rms_hist: collections.deque[float] = collections.deque(maxlen=125)  # ~10 s
        self._started = False

    # ── ciclo de vida ──
    def start(self) -> None:
        if not self._started:
            self._started = True
            threading.Thread(target=self._run, name="mic-hub", daemon=True).start()

    def _cmd(self) -> list[str]:
        cmd = ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16",
               "--latency", "80ms",
               "-P", "{ node.name = jarvis-mic node.description = \"JARVIS micrófono\" "
                     "application.name = JARVIS media.role = Communication }"]
        if self.target:
            cmd += ["--target", self.target]
        return cmd + ["-"]

    def _run(self) -> None:
        backoff = 1.0
        while True:
            t0 = time.time()
            try:
                env = {k: v for k, v in os.environ.items() if k != "PIPEWIRE_PROPS"}  # son los de la voz
                self._proc = subprocess.Popen(self._cmd(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
                print(f"[Mic] Capturando de {self.target or 'la fuente por defecto'} (PipeWire, 16 kHz mono).")
                out = self._proc.stdout
                while True:
                    buf = out.read(_BYTES)
                    if not buf or len(buf) < _BYTES:
                        break
                    pcm = np.frombuffer(buf, dtype=np.int16)
                    rms = float(np.sqrt(np.mean((pcm.astype(np.float32) / 32768) ** 2)))
                    self._rms_hist.append(rms)
                    with self._lock:
                        subs = list(self._subs)
                    for q in subs:
                        try:
                            q.put_nowait(pcm)
                        except queue.Full:  # consumidor lento: se descarta lo más viejo
                            try:
                                q.get_nowait()
                                q.put_nowait(pcm)
                            except (queue.Empty, queue.Full):
                                pass
            except FileNotFoundError:
                print("[Mic] Falta pw-record (paquete pipewire).")
            except Exception as e:
                print(f"[Mic] Error de captura: {e}")
            finally:
                if self._proc and self._proc.poll() is None:
                    self._proc.kill()
            backoff = 1.0 if time.time() - t0 > 10 else min(backoff * 2, 10.0)
            print(f"[Mic] La captura se cortó; reintento en {backoff:.0f} s.")
            time.sleep(backoff)

    # ── suscripción ──
    def subscribe(self, maxsize: int = 64) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def noise_floor(self) -> float:
        """RMS típico del ruido de la sala (0..1). 0.01 si aún no hay datos."""
        h = list(self._rms_hist)
        return float(np.percentile(h, 20)) if len(h) >= 12 else 0.01


_hub: MicHub | None = None


def get_hub() -> MicHub:
    global _hub
    if _hub is None:
        from pathlib import Path
        import yaml
        cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
        _hub = MicHub(target=(cfg.get("audio") or {}).get("mic_target"))
        _hub.start()
    return _hub
