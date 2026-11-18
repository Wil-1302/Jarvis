"""Banco de pruebas del filtro del audio del PC (D-021). Solo para medir; face no lo usa.

    python -m jarvis.eco_banco grabar DIR NOMBRE SEGUNDOS [--reproducir archivo.s16]   (48 kHz mono s16)

Graba a la vez el micrófono (crudo) y el monitor de la salida por defecto (lo que suena por los altavoces), ambos a
16 kHz mono, y los guarda en DIR/NOMBRE.npz (mic, ref y la diferencia de arranque). Las grabaciones contienen la
sala: se guardan con permisos 600 y se borran al acabar la evaluación.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import numpy as np

RATE = 16000


def salida_por_defecto() -> str:
    return subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3).stdout.strip()


def _cmd(target: str, monitor: bool, nombre: str) -> list[str]:
    props = f"{{ node.name = {nombre} application.name = JARVIS{' stream.capture.sink = true' if monitor else ''} }}"
    return ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "--latency", "20ms",
            "--target", target, "-P", props, "-"]


class Captura:
    def __init__(self, target: str, monitor: bool, nombre: str):
        env = {k: v for k, v in os.environ.items() if k != "PIPEWIRE_PROPS"}
        self.p = subprocess.Popen(_cmd(target, monitor, nombre), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        self.trozos: list[bytes] = []
        self.t0: float | None = None
        threading.Thread(target=self._leer, daemon=True).start()

    def _leer(self):
        while True:
            b = self.p.stdout.read(640)  # 20 ms
            if not b:
                break
            if self.t0 is None:
                self.t0 = time.monotonic() - len(b) / 2 / RATE
            self.trozos.append(b)

    def parar(self) -> np.ndarray:
        self.p.terminate()
        self.p.wait(timeout=3)
        return np.frombuffer(b"".join(self.trozos), np.int16)


def grabar(directorio: str, nombre: str, segundos: float, reproducir: str | None = None,
           mic_target: str = "alsa_input.pci-0000_05_00.6.analog-stereo") -> str:
    ref = Captura(salida_por_defecto(), True, "jarvis-banco-ref")
    mic = Captura(mic_target, False, "jarvis-banco-mic")
    time.sleep(0.5)
    pl = None
    if reproducir:
        pl = subprocess.Popen(["pw-play", "--raw", "--rate", "48000", "--channels", "1", "--format", "s16",
                               "-P", "{ media.name = jarvis-banco-video }", reproducir])
    time.sleep(segundos)
    if pl:
        pl.terminate()
    time.sleep(0.3)
    r, m = ref.parar(), mic.parar()
    os.makedirs(directorio, mode=0o700, exist_ok=True)
    ruta = os.path.join(directorio, f"{nombre}.npz")
    np.savez(ruta, mic=m, ref=r, d0=(mic.t0 or 0) - (ref.t0 or 0))
    os.chmod(ruta, 0o600)
    print(f"{ruta}: mic {len(m) / RATE:.1f} s, ref {len(r) / RATE:.1f} s, arranque mic−ref {((mic.t0 or 0) - (ref.t0 or 0)) * 1000:.0f} ms")
    return ruta


# ─── Evaluación sin conexión ───────────────────────────────────────────────────────────────────────────────

def alinear(d: dict) -> tuple[np.ndarray, np.ndarray]:
    """(mic, ref) de la misma duración y con el mismo origen de tiempo (según el arranque de cada captura)."""
    mic, ref = d["mic"].astype(np.int16), d["ref"].astype(np.int16)
    k = int(round(float(d["d0"]) * RATE))   # el mic arrancó k muestras después que la referencia
    ref = ref[k:] if k > 0 else np.concatenate([np.zeros(-k, np.int16), ref])
    n = min(len(mic), len(ref))
    return mic[:n], ref[:n]


def retardo(mic: np.ndarray, ref: np.ndarray, max_ms: int = 400) -> int:
    """Retardo acústico ref→mic (muestras) por GCC-PHAT sobre todo el tramo."""
    n = 1 << int(np.ceil(np.log2(len(mic) + len(ref))))
    X = np.fft.rfft(mic.astype(float), n) * np.conj(np.fft.rfft(ref.astype(float), n))
    cc = np.fft.irfft(X / (np.abs(X) + 1e-9), n)
    m = int(max_ms * RATE / 1000)
    return int(np.argmax(cc[:m]))


def coherencia(seg: np.ndarray, ref_seg: np.ndarray) -> float:
    """Coherencia media (0..1) entre lo captado y la referencia en 200–4000 Hz."""
    from scipy.signal import coherence
    if len(seg) < 2048 or np.abs(ref_seg).max() < 30:
        return 0.0
    f, c = coherence(seg.astype(float), ref_seg.astype(float), fs=RATE, nperseg=512)
    b = (f >= 200) & (f <= 4000)
    return float(np.mean(c[b]))


def _db(x: np.ndarray) -> float:
    return 10 * np.log10(np.mean(x.astype(float) ** 2) + 1.0)


def segmentos(audio: np.ndarray) -> list[tuple[int, int]]:
    from jarvis.vad import Segmenter
    seg = Segmenter(end_silence=0.7, max_seconds=8.0)
    out, blk = [], 1280
    for i in range(0, len(audio) - blk + 1, blk):
        for u in seg.feed(audio[i:i + blk], (i + blk) / RATE):
            a = int(u.t_start * RATE)
            out.append((max(0, a), min(len(audio), a + len(u.audio))))
    return out


def analizar(mic: np.ndarray, ref: np.ndarray, guion: list[str] | None = None, aec_kw: dict | None = None) -> dict:
    """Corre las opciones sobre una grabación y devuelve, por segmento, rasgos y transcripciones."""
    from difflib import SequenceMatcher
    from jarvis.eco import Aec
    from jarvis.nombre import detectar
    from jarvis.stt import transcribe_audio
    aec = Aec(**(aec_kw or {}))
    limpio = aec.proceso(ref, mic)
    mic, ref = mic[:len(limpio)], ref[:len(limpio)]
    lag = retardo(mic, ref) if np.abs(ref).max() > 100 else 0
    ref_d = np.concatenate([np.zeros(lag, np.int16), ref])[:len(ref)]

    def etiqueta(t: str) -> str:
        if not guion:
            return ""
        best = max(guion, key=lambda g: SequenceMatcher(None, g.lower(), t.lower()).ratio())
        r = SequenceMatcher(None, best.lower(), t.lower()).ratio()
        return f"{r:.2f}|{best}" if r >= 0.5 else f"{r:.2f}|[otro]"

    res = {"lag_ms": lag * 1000 / RATE, "erle_total_db": _db(mic) - _db(limpio), "fuentes": {}}
    for fuente, audio in (("crudo", mic), ("limpio", limpio)):
        filas = []
        for a, b in segmentos(audio):
            raw, cl, rf = mic[a:b], limpio[a:b], ref_d[a:b]
            t_raw = transcribe_audio(raw.astype(np.float32) / 32768).strip()
            t_cl = transcribe_audio(cl.astype(np.float32) / 32768).strip()
            filas.append({"t": a / RATE, "dur": (b - a) / RATE,
                          "reduccion_db": _db(raw) - _db(cl),            # cuánto quitó el AEC en esa frase
                          "ref_db": _db(rf), "coh": coherencia(raw, rf),
                          "nombre_crudo": detectar(t_raw)[0], "nombre_limpio": detectar(t_cl)[0],
                          "guion_crudo": etiqueta(t_raw), "guion_limpio": etiqueta(t_cl),
                          "palabras_crudo": len(t_raw.split()), "palabras_limpio": len(t_cl.split())})
        res["fuentes"][fuente] = filas
    res["limpio"] = limpio
    return res


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "grabar":
        rep = sys.argv[sys.argv.index("--reproducir") + 1] if "--reproducir" in sys.argv else None
        grabar(sys.argv[2], sys.argv[3], float(sys.argv[4]), rep)
    else:
        print(__doc__)
