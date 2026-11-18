"""Conversación natural: VAD Silero + Whisper turbo + nombre "Jarvis" en la frase.

Estados:
- ESPERA: cada frase (VAD) se transcribe; solo se atiende si empieza llamando a Jarvis (jarvis.nombre).
  Lo que se oye sin nombre NO se registra ni se envía a ningún sitio.
- CONVERSACIÓN: tras atender, sigue escuchando sin nombre hasta una despedida ("gracias, eso es todo",
  "ya está", "cierra la conversación") o `silencio_fin` segundos sin hablar. Los demás sonidos siguen
  bajados (ducking) mientras dura.
- Mientras JARVIS habla, el micrófono se ignora (semidúplex): no se escucha a sí mismo. Con
  `audio.barge_in: true` (solo si hay cancelación de eco) se puede interrumpir con "para" o con el nombre.

Atajo (Super+J): en espera abre la conversación con un sonido; si está hablando o pensando, lo detiene.
"""
from __future__ import annotations

import queue
import random
import threading
import time
from pathlib import Path

import yaml

from jarvis import ducking, tts
from jarvis.frases import Frases, clasificar, es_despedida, sonido
from jarvis.nombre import detectar

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
ESPERA, CONVERSACION = "espera", "conversacion"


def _cfg() -> dict:
    return yaml.safe_load(open(_CONFIG_PATH, encoding="utf-8"))


class Conversacion:
    def __init__(self, procesar, broadcast, abortar, abort_event, es_parada):
        """procesar(texto, on_delta) → (respuesta, respaldo); el resto son ganchos de main.py."""
        c = _cfg()
        conv = c.get("conversacion") or {}
        self.silencio_fin = float(conv.get("silencio_fin", 10))
        self.fin_frase = float(conv.get("fin_frase", 0.7))
        self.barge_in = bool((c.get("audio") or {}).get("barge_in", False))
        self.duck_factor = float((c.get("audio") or {}).get("ducking", 0.2))
        self.debug = bool(conv.get("debug", False))  # traza de VAD (duraciones, nunca el contenido)
        self.procesar, self.broadcast, self.abortar = procesar, broadcast, abortar
        self.abort_event, self.es_parada = abort_event, es_parada
        self.estado = ESPERA
        self.ocupado = threading.Event()       # pensando o hablando
        self.deadline = 0.0
        self.q: queue.Queue = queue.Queue(maxsize=4)
        self._lock = threading.RLock()
        self.frases = Frases(tts.get_engine())

    # ── HUD ──
    def _hud(self, fase: str) -> None:
        self.broadcast({"type": "state", "state": fase, "conversation": self.estado == CONVERSACION})

    # ── Entrar / salir ──
    def _entrar(self) -> None:
        with self._lock:
            if self.estado == CONVERSACION:
                return
            self.estado = CONVERSACION
            ducking.duck(self.duck_factor)
            print("[Conv] En conversación.")

    def _salir(self, con_sonido=True) -> None:
        with self._lock:
            if self.estado == ESPERA:
                return
            self.estado = ESPERA
        if con_sonido:
            tts.play_audio(sonido("fin", tts.get_engine().rate))
        ducking.unduck()
        tts.player.close()
        print("[Conv] En espera.")
        self._hud("idle")

    def _escuchando(self) -> None:
        self.deadline = time.time() + self.silencio_fin
        self._hud("listening")

    # ── Atajo ──
    def trigger(self, source: str = "atajo") -> None:
        if self.ocupado.is_set():
            self.abortar()
            print(f"[Conv] Detenido ({source}).")
            return
        self._entrar()
        tts.play_audio(sonido("activo", tts.get_engine().rate))
        self._escuchando()

    # ── Escucha (hilo) ──
    def run_listener(self) -> None:
        from jarvis.mic import get_hub
        from jarvis.vad import Segmenter
        hub = get_hub()
        mq = hub.subscribe()
        seg = Segmenter(end_silence=self.fin_frase, max_seconds=8.0)
        silenciado = False
        while True:
            try:
                pcm = mq.get(timeout=0.5)
            except queue.Empty:
                pcm = None
            now = time.time()
            hablando = tts.is_speaking() or now < tts.player.busy_until() + 0.35
            if hablando and not self.barge_in:
                if not silenciado:
                    seg.reset()
                    silenciado = True
                continue
            if silenciado:
                silenciado = False
                seg.reset()
                with mq.mutex:
                    mq.queue.clear()  # descarta lo captado mientras hablaba
                continue
            if pcm is not None:
                seg.max_frames = int((20.0 if self.estado == CONVERSACION else 8.0) * 16000 / 512)
                for u in seg.feed(pcm, now):
                    if self.debug:
                        print(f"[VAD] frase de {u.seconds:.1f} s ({self.estado}{', ocupado' if self.ocupado.is_set() else ''})")
                    if self.ocupado.is_set() and not self.barge_in:
                        continue
                    try:
                        self.q.put_nowait(u)
                    except queue.Full:
                        pass
            if (self.estado == CONVERSACION and not self.ocupado.is_set() and not seg.in_speech
                    and self.q.empty() and now > self.deadline):
                print(f"[Conv] {self.silencio_fin:.0f} s de silencio.")
                threading.Thread(target=self._salir, daemon=True).start()
                self.deadline = float("inf")

    # ── Atención (hilo) ──
    def run_worker(self) -> None:
        from jarvis.stt import transcribe_audio
        while True:
            u = self.q.get()
            hablando = self.ocupado.is_set()
            t_stt0 = time.time()
            texto = transcribe_audio(u.audio).strip()
            t_stt = time.time() - t_stt0
            if not texto:
                continue
            if hablando:  # barge-in (solo con cancelación de eco)
                if self.es_parada(texto) or detectar(texto)[0]:
                    self.abortar()
                continue
            if self.estado == ESPERA:
                llama, resto = detectar(texto)
                if not llama:
                    if self.debug:
                        print(f"[VAD] sin nombre ({len(texto.split())} palabras, STT {t_stt:.2f} s)")
                    continue  # sin nombre: ni se registra ni se envía
                self._entrar()
            else:
                resto = texto
                llama2, r2 = detectar(texto)
                if llama2:
                    resto = r2
            tiempos = {"fin_frase": u.t_emit - u.t_end, "stt": t_stt}
            print(f"[Usted] {texto}")
            self.broadcast({"type": "user", "text": texto})
            try:
                self.ocupado.set()
                self.abort_event.clear()
                self._atender(resto, tiempos, u)
            except Exception as e:
                import traceback
                print(f"[ERROR] {e}")
                traceback.print_exc()
            finally:
                self.ocupado.clear()
                self.abort_event.clear()
            if self.estado == CONVERSACION:
                self._escuchando()

    def _atender(self, resto: str, tiempos: dict, u) -> None:
        rate = tts.get_engine().rate
        if self.estado == CONVERSACION and (es_despedida(resto) or self.es_parada(resto)):
            texto, audio = self.frases.elegir("despedida")
            print(f"[Jarvis] {texto}")
            self.broadcast({"type": "response", "text": texto})
            self._hud("speaking")
            tts.play_audio(audio, rate)
            self._salir(con_sonido=False)
            return
        cat = clasificar(resto)
        if cat:
            if cat == "llamada" and random.random() < 0.5:
                tts.play_audio(sonido("activo", rate))
                tiempos["respuesta"] = time.time() - u.t_end
            else:
                texto, audio = self.frases.elegir(cat)
                print(f"[Jarvis] {texto}")
                self.broadcast({"type": "response", "text": texto})
                self._hud("speaking")
                tiempos["respuesta"] = time.time() - u.t_end
                tts.play_audio(audio, rate)
            print("[Tiempos] " + " · ".join(f"{k} {v:.2f}s" for k, v in tiempos.items()) + " (local)")
            return
        # Orden para el cerebro: streaming → voz por oraciones
        self._hud("thinking")
        deltas: queue.Queue = queue.Queue()
        t_brain0 = time.time()
        marca = {}
        resultado = {}

        def cerebro():
            def on_delta(d):
                marca.setdefault("primer_token", time.time() - t_brain0)
                deltas.put(d)
            try:
                resultado["r"] = self.procesar(resto, on_delta)
            except Exception as e:
                resultado["e"] = e
            finally:
                deltas.put(None)

        threading.Thread(target=cerebro, daemon=True).start()

        def chunks():
            while True:
                d = deltas.get()
                if d is None or self.abort_event.is_set():
                    return
                yield d

        def primer_audio():
            marca["primer_audio"] = time.time() - u.t_end
            self._hud("speaking")

        dicho = tts.speak_stream(chunks(), on_first_audio=primer_audio)
        if "e" in resultado and not dicho:
            msg = resultado["e"].args[0] if resultado["e"].args else "Lo siento, señor, algo ha fallado."
            dicho = msg if isinstance(msg, str) and msg.startswith(("Señor", "Lo siento")) else "Lo siento, señor, algo ha fallado."
            tts.speak(dicho)
        print(f"[Jarvis] {dicho}")
        self.broadcast({"type": "response", "text": dicho})
        tiempos.update({"cerebro_1er_token": marca.get("primer_token", float("nan")),
                        "voz_desde_fin_de_frase": marca.get("primer_audio", float("nan")),
                        "total": time.time() - u.t_end})
        print("[Tiempos] " + " · ".join(f"{k} {v:.2f}s" for k, v in tiempos.items()))

    def start(self) -> None:
        threading.Thread(target=self.run_listener, name="escucha", daemon=True).start()
        threading.Thread(target=self.run_worker, name="atencion", daemon=True).start()
        self._hud("idle")
