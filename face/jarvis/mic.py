"""Micrófono compartido + filtro del audio del propio PC (D-021).

Captura con `pw-record` (cliente nativo de PipeWire) en vez de PortAudio/ALSA:
- Apunta a un nodo concreto (`audio.mic_target`, el micrófono del portátil). Si no existe, NO se usa la fuente por
  defecto (`node.dont-fallback`): la captura reintenta hasta que vuelva.
  Nunca se abre el micrófono Bluetooth (pasaría los audífonos o el parlante a manos libres, HFP).
- 16 kHz mono s16, bloques de 20 ms; PipeWire remuestrea en el propio stream (el grafo sigue a 48 kHz).

Filtro del audio del PC (`audio.filtro_pc: auto`): si la salida por defecto NO son audífonos, se captura también su
monitor (todo lo que suena: vídeos, música, llamadas y la propia voz de JARVIS) y se cancela del micrófono con WebRTC
AEC3 (jarvis.eco). Los suscriptores reciben la señal LIMPIA; la original queda en un anillo de ~30 s accesible por
índice de muestra (`tramo`). Con audífonos, o sin la librería, limpio = original.

Los suscriptores reciben tuplas (índice de la 1.ª muestra, bloque int16).
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
BLOCK = 320            # 20 ms
_BYTES = BLOCK * 2
_ANILLO = 30 * RATE    # ~30 s de audio original


def _env() -> dict:
    return {k: v for k, v in os.environ.items() if k != "PIPEWIRE_PROPS"}  # PIPEWIRE_PROPS son los de la voz


class _Captura:
    """Un pw-record leyendo en su hilo; guarda lo leído con su índice absoluto y la hora de la 1.ª muestra."""

    def __init__(self, cmd: list[str], nombre: str):
        self.cmd, self.nombre = cmd, nombre
        self.t0: float | None = None
        self.n = 0
        self.buf: collections.deque[tuple[int, np.ndarray]] = collections.deque(maxlen=200)  # ~4 s
        self.vivo = True
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_env())
        self.cond = threading.Condition()
        threading.Thread(target=self._leer, name=nombre, daemon=True).start()

    def _leer(self):
        out = self.p.stdout
        while self.vivo:
            b = out.read(_BYTES)
            if not b or len(b) < _BYTES:
                break
            pcm = np.frombuffer(b, dtype=np.int16)
            with self.cond:
                if self.t0 is None:
                    self.t0 = time.monotonic() - len(pcm) / RATE
                self.buf.append((self.n, pcm))
                self.n += len(pcm)
                self.cond.notify_all()
        self.vivo = False
        with self.cond:
            self.cond.notify_all()

    def leer(self, i0: int, n: int) -> np.ndarray | None:
        """Muestras [i0, i0+n) si ya están (ceros donde falten por delante); None si aún no han llegado."""
        with self.cond:
            if not self.buf or self.n < i0 + n:
                return None
            out = np.zeros(n, np.int16)
            for j, blk in self.buf:
                a, b = max(i0, j), min(i0 + n, j + len(blk))
                if a < b:
                    out[a - i0:b - i0] = blk[a - j:b - j]
            return out

    def parar(self):
        self.vivo = False
        try:
            self.p.terminate()
        except Exception:
            pass


class MicHub:
    def __init__(self, target: str | None = None, filtro: str = "auto", parlantes=(), audifonos=()):
        self.target, self.filtro = target, filtro
        self.parlantes, self.audifonos = list(parlantes or ()), list(audifonos or ())
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._rms_hist: collections.deque[float] = collections.deque(maxlen=500)  # ~10 s
        self._anillo = np.zeros(_ANILLO, np.int16)
        self.n = 0                       # muestras de micrófono recibidas (índice absoluto)
        self._ref: _Captura | None = None
        self._ref_sink: str | None = None
        self._aec = None
        self.estado_filtro = "apagado"   # apagado | audífonos | activo | sin-librería
        # Traza del filtro (JARVIS_TRAZA_FILTRO=1): solo números, nunca audio ni texto.
        self._traza = os.environ.get("JARVIS_TRAZA_FILTRO") == "1"
        self._diag = {"n": 0, "sin_ref": 0, "e_in": 0.0, "e_out": 0.0, "e_ref": 0.0, "desfase": 0, "t": time.monotonic()}
        self._started = False

    # ── ciclo de vida ──
    def start(self) -> None:
        if not self._started:
            self._started = True
            threading.Thread(target=self._run, name="mic-hub", daemon=True).start()
            if self.filtro != "off":
                threading.Thread(target=self._vigilar_salida, name="mic-salida", daemon=True).start()

    def _cmd_mic(self) -> list[str]:
        cmd = ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "--latency", "20ms",
               "-P", "{ node.name = jarvis-mic node.description = \"JARVIS micrófono\" "
                     "application.name = JARVIS media.role = Communication"
                     # Fijado al micrófono del portátil: si no está, NO caer en la fuente por defecto (que podría ser
                     # el micrófono de un parlante/audífonos BT y pasarlos a manos libres); la captura reintenta.
                     + (" node.dont-fallback = true node.dont-reconnect = true" if self.target else "") + " }"]
        if self.target:
            cmd += ["--target", self.target]
        return cmd + ["-"]

    @staticmethod
    def _cmd_ref(sink: str) -> list[str]:
        return ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16", "--latency", "20ms",
                "--target", sink, "-P", "{ node.name = jarvis-referencia node.description = \"JARVIS referencia\" "
                "application.name = JARVIS stream.capture.sink = true }", "-"]

    # ── filtro: sigue a la salida por defecto (altavoces ↔ audífonos) ──
    def _vigilar_salida(self) -> None:
        from jarvis import eco
        while True:
            try:
                sink = eco.salida_por_defecto()
                nombre = (sink or {}).get("name")
                if not eco.disponible():
                    nuevo = "sin-librería"
                elif sink is None:
                    nuevo = "apagado"
                elif eco.es_audifonos(sink, self.parlantes, self.audifonos):
                    nuevo = "audífonos"
                else:
                    nuevo = "activo"
                if nuevo != "activo" and self._ref is not None:
                    self._quitar_ref()
                if nuevo == "activo" and (self._ref is None or self._ref_sink != nombre or not self._ref.vivo):
                    self._poner_ref(nombre)
                if nuevo != self.estado_filtro:
                    print(f"[Mic] Filtro del audio del PC: {nuevo}" + (f" ({nombre})" if nombre else ""))
                    self.estado_filtro = nuevo
            except Exception as e:
                print(f"[Mic] Vigilancia de la salida: {e}")
            time.sleep(3.0)

    def _poner_ref(self, sink: str) -> None:
        from jarvis.eco import Aec
        self._quitar_ref()
        with self._lock:
            self._aec = Aec()
            self._ref = _Captura(self._cmd_ref(sink), "mic-referencia")
            self._ref_sink = sink

    def _quitar_ref(self) -> None:
        with self._lock:
            if self._ref is not None:
                self._ref.parar()
            self._ref, self._aec, self._ref_sink = None, None, None

    def _limpiar(self, i0: int, raw: np.ndarray, t_mic0: float) -> np.ndarray:
        """Cancela del bloque de micrófono lo que sonaba por la salida en ese mismo instante."""
        with self._lock:
            ref, aec = self._ref, self._aec
        if ref is None or aec is None or ref.t0 is None:
            return raw
        j = i0 + int(round((t_mic0 - ref.t0) * RATE))     # misma hora en la referencia
        r = None
        # La referencia de un parlante Bluetooth llega a ráfagas (hasta ~120 ms tarde): se espera ≤ 250 ms en vez de
        # rellenar con ceros (con 40 ms, el 16 % de los bloques iban sin referencia y el AEC no convergía, 18/11). El
        # micrófono se acumula mientras tanto en su búfer (4 s) y se procesa al llegar: no se pierde audio.
        for _ in range(25):
            r = ref.leer(j, len(raw))
            if r is not None:
                break
            with ref.cond:
                ref.cond.wait(0.01)
        if r is None:
            r = np.zeros(len(raw), np.int16)
            self._diag["sin_ref"] += 1
        out = aec.proceso(r, raw)
        self._diag_bloque(aec, raw, out, r, ref.n - (j + len(raw)))
        if len(out) < len(raw):   # arranque del AEC (tramas de 10 ms): se rellena para mantener el índice
            out = np.concatenate([np.zeros(len(raw) - len(out), np.int16), out])
        return out[-len(raw):]

    def _diag_bloque(self, aec, raw, out, r, desfase) -> None:
        if not self._traza:
            return
        d = self._diag
        f = lambda x: float(np.mean((x.astype(np.float32) / 32768) ** 2))
        d["n"] += 1
        d["e_in"] += f(raw); d["e_out"] += f(out[-len(raw):]) if len(out) else 0.0; d["e_ref"] += f(r)
        d["desfase"] = desfase
        if time.monotonic() - d["t"] >= 5.0:
            db = lambda e: 10 * np.log10(e / max(d["n"], 1) + 1e-12)
            erle, dl = aec.stats()
            print(f"[Filtro] 5 s: mic {db(d['e_in']):.1f} → limpio {db(d['e_out']):.1f} dBFS · parlante "
                  f"{db(d['e_ref']):.1f} · sin referencia {d['sin_ref']}/{d['n']} bloques · ref lleva "
                  f"{d['desfase']/16:.0f} ms de margen · AEC retardo {dl} ms, ERLE {erle:.1f} dB")
            self._diag = {"n": 0, "sin_ref": 0, "e_in": 0.0, "e_out": 0.0, "e_ref": 0.0, "desfase": 0,
                          "t": time.monotonic()}

    def _run(self) -> None:
        backoff = 1.0
        while True:
            t0 = time.time()
            cap = None
            try:
                cap = _Captura(self._cmd_mic(), "mic-captura")
                print(f"[Mic] Capturando de {self.target or 'la fuente por defecto'} (PipeWire, 16 kHz mono).")
                zeros, i = 0, cap.n
                while True:
                    with cap.cond:
                        while cap.vivo and cap.n <= i:
                            cap.cond.wait(0.5)
                        if cap.n <= i:
                            break
                        bloques = [(j, b) for j, b in cap.buf if j >= i]
                    for j, pcm in bloques:
                        i = j + len(pcm)
                        rms = float(np.sqrt(np.mean((pcm.astype(np.float32) / 32768) ** 2)))
                        self._rms_hist.append(rms)
                        zeros = zeros + 1 if rms == 0.0 else 0
                        if zeros == 200:  # 4 s de ceros exactos: micrófono silenciado
                            self._aviso_silenciado()
                        idx = self.n
                        k = idx % _ANILLO
                        m = min(len(pcm), _ANILLO - k)
                        self._anillo[k:k + m] = pcm[:m]
                        self._anillo[:len(pcm) - m] = pcm[m:]
                        self.n += len(pcm)
                        limpio = self._limpiar(j, pcm, cap.t0 or time.monotonic())
                        self._publicar(idx, limpio)
            except FileNotFoundError:
                print("[Mic] Falta pw-record (paquete pipewire).")
            except Exception as e:
                print(f"[Mic] Error de captura: {e}")
            finally:
                if cap is not None:
                    cap.parar()
            backoff = 1.0 if time.time() - t0 > 10 else min(backoff * 2, 10.0)
            print(f"[Mic] La captura se cortó; reintento en {backoff:.0f} s.")
            time.sleep(backoff)

    def _publicar(self, idx: int, pcm: np.ndarray) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait((idx, pcm))
            except queue.Full:  # consumidor lento: se descarta lo más viejo
                try:
                    q.get_nowait()
                    q.put_nowait((idx, pcm))
                except (queue.Empty, queue.Full):
                    pass

    def tramo(self, i0: int, i1: int) -> np.ndarray:
        """Audio ORIGINAL (sin filtrar) de las muestras [i0, i1), si sigue en el anillo (últimos ~30 s)."""
        i0 = max(i0, self.n - _ANILLO)
        if i1 <= i0:
            return np.zeros(0, np.int16)
        idx = np.arange(i0, i1) % _ANILLO
        return self._anillo[idx].copy()

    def _aviso_silenciado(self) -> None:
        msg = "El micrófono está silenciado: JARVIS no le oye."
        try:
            if self.target:
                r = subprocess.run(["pactl", "get-source-mute", self.target], capture_output=True, text=True, timeout=3)
                if "yes" not in r.stdout:
                    msg = "El micrófono solo envía silencio (¿desconectado o silenciado por hardware?)."
            subprocess.Popen(["notify-send", "-a", "JARVIS", "-i", "microphone-sensitivity-muted", "JARVIS", msg])
        except Exception:
            pass
        print(f"[Mic] {msg}")

    # ── suscripción ──
    def subscribe(self, maxsize: int = 250) -> queue.Queue:
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
        return float(np.percentile(h, 20)) if len(h) >= 50 else 0.01

    @property
    def filtrando(self) -> bool:
        return self.estado_filtro == "activo"


_hub: MicHub | None = None


def modo_filtro(v) -> str:
    """`audio.filtro_pc` → "auto" | "off". Ojo: en YAML, `off`/`no` sin comillas llegan como False (18/11: el filtro
    seguía activo con `filtro_pc: off`)."""
    if v is False or v is None or str(v).strip().lower() in ("off", "false", "no", "0"):
        return "off"
    return "auto"


def get_hub() -> MicHub:
    global _hub
    if _hub is None:
        from pathlib import Path
        import yaml
        cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
        a = cfg.get("audio") or {}
        _hub = MicHub(target=a.get("mic_target"), filtro=modo_filtro(a.get("filtro_pc", "auto")),
                      parlantes=a.get("parlantes") or (), audifonos=a.get("audifonos") or ())
        _hub.start()
    return _hub
