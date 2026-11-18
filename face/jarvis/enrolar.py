"""Grabación guiada de la voz del señor y medición de falsos rechazos / falsos aceptos (D-015).

Uso (en una terminal, frente al portátil):
    scripts/jarvis-voz enrolar          # 12 frases con cuenta atrás → ~/.config/jarvis/voz.npz (600)
    scripts/jarvis-voz medir            # condiciones reales → tabla y umbral sugerido
    scripts/jarvis-voz medir --aplicar  # además guarda el umbral sugerido en la huella

No se guarda audio en ningún momento: cada toma se convierte en un vector y el audio se descarta.
Mientras corre, jarvis-face se detiene (para que no atienda las frases de prueba) y luego se reanuda.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import time

import numpy as np

from jarvis import hablante
from jarvis.mic import MicHub
from jarvis.vad import Segmenter

FRASES = [
    "Jarvis, ¿estás despierto?",
    "Pon algo de música tranquila, por favor.",
    "Jarvis, abre la calculadora.",
    "¿Qué tiempo va a hacer mañana por la tarde?",
    "Sube un poco el volumen de la música.",
    "Jarvis, necesito que me ayudes con un documento.",
    "Recuérdame que mañana tengo que estudiar redes.",
    "¿Cuánto es doscientos treinta por cuatro?",
    "Jarvis, reproduce algo de rock en Spotify.",
    "Escribe un correo corto para mi profesor.",
    "Gracias, eso es todo por ahora.",
    "Jarvis, cuéntame una curiosidad sobre el espacio.",
]
MEDIR = {
    "normal": "Normal, a su distancia de siempre",
    "ruido": "Con ruido: ponga música o un vídeo de fondo a volumen medio (por los audífonos NO vale: que suene en la sala)",
    "distancia": "A distancia: aléjese 2–3 metros del portátil",
    "cansada": "Con voz cansada o baja, como al final del día",
}
MIC = "alsa_input.pci-0000_05_00.6.analog-stereo"


def _tono(f=880, d=0.12):
    try:
        import sounddevice as sd
        t = np.arange(int(24000 * d)) / 24000
        sd.play((0.25 * np.sin(2 * np.pi * f * t) * np.minimum(1, (d - t) * 40)).astype(np.float32), 24000)
        sd.wait()
    except Exception:
        pass


def _notify(msg):
    subprocess.run(["notify-send", "-a", "JARVIS", "-t", "4000", "JARVIS · voz", msg], check=False)


class Grabador:
    def __init__(self):
        self.hub = MicHub(target=MIC)
        self.hub.start()
        self.q = self.hub.subscribe(maxsize=400)
        time.sleep(1.0)

    def frase(self, espera=6.0, maxima=9.0) -> np.ndarray | None:
        """Espera a que hable y devuelve la frase (o None si no habló)."""
        with self.q.mutex:
            self.q.queue.clear()
        seg = Segmenter(end_silence=0.8, max_seconds=maxima)
        t0 = time.time()
        while time.time() - t0 < espera + maxima:
            try:
                pcm = self.q.get(timeout=0.5)[1]
            except queue.Empty:
                continue
            us = seg.feed(pcm)
            if us:
                return max(us, key=lambda u: u.seconds).audio
            if not seg.in_speech and time.time() - t0 > espera:
                return None
        return None

    def continuo(self, segundos: float) -> list[np.ndarray]:
        with self.q.mutex:
            self.q.queue.clear()
        seg = Segmenter(end_silence=0.7, max_seconds=6.0)
        out, t0 = [], time.time()
        while time.time() - t0 < segundos:
            try:
                out += [u.audio for u in seg.feed(self.q.get(timeout=0.5)[1])]
            except queue.Empty:
                pass
        return out


def _cuenta_atras(texto: str, n: int, total: int) -> None:
    print(f"\n  [{n}/{total}]  Lea en voz alta:\n\n      «{texto}»\n")
    _notify(f"{n}/{total}: «{texto}»")
    for k in (3, 2, 1):
        print(f"      {k}…", flush=True)
        time.sleep(0.8)
    _tono()
    print("      ¡Ahora!", flush=True)


def _face(accion: str) -> bool:
    activo = subprocess.run(["systemctl", "--user", "is-active", "-q", "jarvis-face"]).returncode == 0
    if accion == "stop" and activo:
        subprocess.run(["systemctl", "--user", "stop", "jarvis-face"], check=False)
    if accion == "start":
        subprocess.run(["systemctl", "--user", "start", "jarvis-face"], check=False)
    return activo


def _mic_ok() -> bool:
    r = subprocess.run(["pactl", "get-source-mute", MIC], capture_output=True, text=True)
    if "yes" in r.stdout:
        print("  ✘ El micrófono del portátil está silenciado. Actívelo y vuelva a empezar.")
        return False
    return True


def enrolar() -> None:
    print("JARVIS · grabación de su voz (no se guarda audio; solo una huella numérica en ~/.config/jarvis/voz.npz)")
    if not _mic_ok():
        return
    estaba = _face("stop")
    try:
        ex, g = hablante.Extractor(), Grabador()
        embs = []
        for i, f in enumerate(FRASES, 1):
            for intento in range(2):
                _cuenta_atras(f, i, len(FRASES))
                a = g.frase()
                if a is not None and len(a) > 0.8 * 16000:
                    embs.append(ex(a))
                    print(f"      ✔ {len(a) / 16000:.1f} s")
                    break
                print("      No le he oído bien; repetimos.")
        if len(embs) < 8:
            print(f"\n  ✘ Solo {len(embs)} tomas válidas (mínimo 8). No se guarda nada.")
            return
        E = np.stack(embs)
        c = E.mean(0)
        c /= np.linalg.norm(c)
        cons = E @ c
        hablante.guardar_huella(embs, umbral=0.62, extra={"consistencia_min": float(cons.min())})
        print(f"\n  ✔ Huella guardada: {len(embs)} tomas · consistencia media {cons.mean():.2f} (mín {cons.min():.2f})")
        print(f"    {hablante.HUELLA} (600). Umbral provisional 0,62 hasta medir: scripts/jarvis-voz medir")
    finally:
        if estaba:
            _face("start")


def _impostores_sinteticos(v: hablante.Verificador) -> list[float]:
    """Voces sintéticas de otras personas (si existe el juego de prueba local; sin descargar nada)."""
    import glob
    import soundfile as sf
    from scipy.signal import resample_poly
    d = os.environ.get("JARVIS_VOCES_PRUEBA", "")
    out = []
    for f in sorted(glob.glob(os.path.join(d, "*.mp3")))[:100] if d else []:
        a, sr = sf.read(f, dtype="float32")
        a = a.mean(1) if a.ndim > 1 else a
        out.append(v.puntuacion(resample_poly(a, 16000, sr).astype(np.float32)))
    return out


def medir(aplicar: bool) -> None:
    v = hablante.cargar()
    if v is None:
        print("Primero: scripts/jarvis-voz enrolar")
        return
    if not _mic_ok():
        return
    estaba = _face("stop")
    res: dict[str, list[float]] = {}
    try:
        g = Grabador()
        frases = FRASES[1::3][:4]
        for cond, desc in MEDIR.items():
            input(f"\n=== {cond.upper()}: {desc}.\n    Pulse Enter cuando esté listo (o Ctrl+C para terminar)… ")
            res[cond] = []
            for i, f in enumerate(frases, 1):
                _cuenta_atras(f, i, len(frases))
                a = g.frase()
                if a is None:
                    print("      (no se oyó)")
                    continue
                ok, p = v.es_el_senor(a)
                res[cond].append(p)
                print(f"      puntuación {p:.2f} {'✔' if ok else '✘'}")
        for cond, desc in [("tv", "Ponga un vídeo o la TV con gente hablando, por los altavoces, 30 s. Usted NO hable"),
                           ("otras_voces", "Si hay otra persona dispuesta (con su permiso), que hable 30 s. Si no, Ctrl+C")]:
            try:
                input(f"\n=== {cond.upper()}: {desc}.\n    Pulse Enter para empezar… ")
            except KeyboardInterrupt:
                print()
                continue
            print("      Escuchando 30 s…", flush=True)
            res[cond] = [v.puntuacion(a) for a in g.continuo(30)]
            print(f"      {len(res[cond])} frases ajenas · máx {max(res[cond], default=0):.2f}")
    except KeyboardInterrupt:
        print("\n(medición interrumpida)")
    finally:
        if estaba:
            _face("start")
    sint = _impostores_sinteticos(v)
    if sint:
        res["sinteticas"] = sint
    _informe(res, v, aplicar)


def _informe(res: dict, v: hablante.Verificador, aplicar: bool) -> None:
    propias = [p for c in MEDIR for p in res.get(c, [])]
    ajenas = [p for c in ("tv", "otras_voces", "sinteticas") for p in res.get(c, [])]
    print("\n  Condición       n   media   mín    máx")
    for c, ps in res.items():
        if ps:
            print(f"  {c:13} {len(ps):3}   {np.mean(ps):.2f}   {min(ps):.2f}   {max(ps):.2f}")
    if not propias:
        return
    # Umbral: punto medio entre la voz ajena más parecida y el 5 % más bajo de las suyas. Si se solapan,
    # gana no aceptar a desconocidos (techo ajeno + 0,02) y se informa del rechazo que eso supone.
    techo = max(ajenas, default=0.35)
    suelo = float(np.percentile(propias, 5))
    umbral = round((techo + suelo) / 2 if suelo > techo else techo + 0.02, 2)
    fr = np.mean([p < umbral for p in propias])
    fa = np.mean([p >= umbral for p in ajenas]) if ajenas else float("nan")
    print(f"\n  Umbral sugerido {umbral:.2f} → falsos rechazos {100 * fr:.0f} % · falsos aceptos {100 * fa:.0f} %"
          f" (actual {v.umbral:.2f})")
    out = hablante.HUELLA.with_name("medidas-voz.json")
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"fecha": time.strftime("%Y-%m-%d %H:%M"), "puntuaciones": res, "umbral_sugerido": umbral}, f)
    if aplicar:
        d = np.load(hablante.HUELLA)
        hablante.guardar_huella(list(d["embs"]), umbral, extra={"medido": time.strftime("%Y-%m-%d %H:%M")})
        print(f"  ✔ Umbral {umbral:.2f} guardado en la huella. Reinicie face: systemctl --user restart jarvis-face")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "enrolar":
        enrolar()
    elif cmd == "medir":
        medir("--aplicar" in sys.argv)
    else:
        print(__doc__)
