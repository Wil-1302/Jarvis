"""Conversación natural: VAD Silero + Whisper turbo + nombre "Jarvis" en la frase.

Estados:
- ESPERA: cada frase (VAD) se transcribe; solo se atiende si empieza llamando a Jarvis (jarvis.nombre).
  Lo que se oye sin nombre NO se registra ni se envía a ningún sitio.
- CONVERSACIÓN: tras atender, sigue escuchando sin nombre hasta una despedida (frases.es_despedida: "adiós", "eso
  es todo", "ya", "gracias", "termina", "cierra la conversación"…) o `silencio_fin` segundos sin hablar. Al cerrar
  vuelve a ESPERA de verdad: `sordera_tras_cierre` s sin escuchar y se vacía la cola (D-022). Los demás sonidos siguen
  bajados (ducking) mientras dura.
- Mientras JARVIS habla, el micrófono se ignora (semidúplex): no se escucha a sí mismo. Con
  `audio.barge_in: true` (solo si hay cancelación de eco) se puede interrumpir con "para" o con el nombre.

Atajo (Super+J): en espera abre la conversación con un sonido; si está hablando o pensando, lo detiene.
"""
from __future__ import annotations

import os
import queue
import random
import threading
import time
from pathlib import Path

import numpy as np
import yaml

from jarvis import ducking, tts
from jarvis.frases import Frases, clasificar, es_despedida, frase_incompleta, sonido
from jarvis.nombre import detectar

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
ESPERA, CONVERSACION = "espera", "conversacion"


class Cancelado(Exception):
    """El señor interrumpió: se corta la respuesta en curso (también la petición al cerebro)."""


def _cfg() -> dict:
    return yaml.safe_load(open(_CONFIG_PATH, encoding="utf-8"))


class Conversacion:
    def __init__(self, procesar, broadcast, abortar, abort_event, es_parada):
        """procesar(texto, on_delta) → (respuesta, respaldo); el resto son ganchos de main.py."""
        c = _cfg()
        conv = c.get("conversacion") or {}
        self.silencio_fin = float(conv.get("silencio_fin", 10))
        self.fin_frase = float(conv.get("fin_frase", 0.45))
        # Frase a medias ("y…", "pero…", "de…"): se espera su continuación hasta este plazo y se unen (D-024).
        self.espera_incompleta = float(conv.get("espera_incompleta", 1.5))
        a = c.get("audio") or {}
        bi = a.get("barge_in", "auto")
        self.barge_in = "auto" if str(bi).lower() == "auto" else bool(bi)
        self.bi_umbral = float(a.get("barge_in_umbral", 0.7))     # prob. de voz (VAD) para contar como interrupción
        self.bi_min_voz = float(a.get("barge_in_min_voz", 0.12))  # s de voz seguida antes de cortar
        self.stt_fuente = str(a.get("stt_fuente", "limpio"))      # limpio | crudo (D-021)
        self.interrumpido = False
        self.hub = None
        self.duck_factor = float((c.get("audio") or {}).get("ducking", 0.2))
        self.debug = bool(conv.get("debug", False))  # traza de VAD (duraciones, nunca el contenido)
        self.procesar, self.broadcast, self.abortar = procesar, broadcast, abortar
        self.abort_event, self.es_parada = abort_event, es_parada
        self.estado = ESPERA
        self.agenda = None                     # jarvis.agenda.Agenda (lo engancha main.py)
        self.ocupado = threading.Event()       # pensando o hablando
        self.deadline = 0.0
        self.sordo_hasta = 0.0                 # tras despedirse, el micrófono se ignora (D-022)
        self.sordera = float(conv.get("sordera_tras_cierre", 2.0))
        self.q: queue.Queue = queue.Queue(maxsize=4)
        self._lock = threading.RLock()
        self.frases = Frases(tts.get_engine())
        # Verificación de hablante (D-015): APAGADA por decisión del señor (D-021: cualquier persona puede hablarle).
        # El código se conserva por si un día se usa solo para autorizar acciones delicadas: `hablante.activo: true`.
        self.verif = None
        self.exento = False  # la 1.ª frase tras Super+J no se verifica (está frente al teclado)
        if not (c.get("hablante") or {}).get("activo", False):
            print("[Voz] Verificación de hablante: apagada (cualquier persona puede hablarle).")
        else:
            from jarvis import hablante
            try:
                self.verif = hablante.cargar((c.get("hablante") or {}).get("umbral"))
            except Exception as e:
                print(f"[Voz] No se pudo cargar la huella: {e}")
            print(f"[Voz] Verificación de hablante: {'activa (umbral %.2f)' % self.verif.umbral if self.verif else 'DESACTIVADA: sin huella (scripts/jarvis-voz enrolar)'}")

    # ── HUD ──
    def _hud(self, fase: str) -> None:
        self.broadcast({"type": "state", "state": fase, "conversation": self.estado == CONVERSACION})

    # ── Entrar / salir ──
    def _entrar(self) -> None:
        with self._lock:
            if self.estado == CONVERSACION:
                return
            self.estado = CONVERSACION
            # Sin plazo hasta que acabe de responder (_escuchando lo fija). Antes quedaba el de la vez anterior (0 al
            # arrancar) y la primera conversación tras reiniciar se cerraba en el acto (18/11).
            self.deadline = float("inf")
            ducking.duck(self.duck_factor)
            print("[Conv] En conversación.")

    def _salir(self, con_sonido=True, sordo=False) -> None:
        """Vuelve a espera. `sordo`: 2 s sin escuchar (despedidas y órdenes que cierran, D-022). Al cerrar por
        silencio NO: si el señor dice «Jarvis» justo entonces, se perdía el principio de la frase (18/11)."""
        with self._lock:
            if self.estado == ESPERA:
                return
            self.estado = ESPERA
        if con_sonido:
            tts.play_audio(sonido("fin", tts.get_engine().rate))
        # Cerrar de verdad: fuera lo que estuviera en cola (y, tras una despedida, 2 s sin escuchar); solo «Jarvis»
        # o Super+J reactivan.
        if sordo:
            self.sordo_hasta = time.time() + self.sordera
        with self.q.mutex:
            self.q.queue.clear()
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
        self.sordo_hasta = 0.0   # Super+J reactiva aunque acabe de despedirse
        self._entrar()
        self.exento = True
        tts.play_audio(sonido("activo", tts.get_engine().rate))
        self._escuchando()

    # ── Avisos proactivos (jarvis/agenda.py) ──
    def anunciar(self, texto: str, sonido_previo: bool = True, espera_max: float = 300) -> bool:
        """Habla sin que se lo pidan (aviso de tareas, alarma) y deja la conversación abierta para que el señor
        conteste sin decir «Jarvis» («ya la entregué», «recuérdamelo en una hora», «empecemos»). No interrumpe:
        si está pensando o hablando, espera hasta `espera_max` s."""
        fin = time.time() + espera_max
        while self.ocupado.is_set():
            if time.time() > fin:
                print("[Conv] Aviso descartado: seguía ocupado.")
                return False
            time.sleep(1)
        self.ocupado.set()
        try:
            self._entrar()
            if sonido_previo:
                tts.play_audio(sonido("activo", tts.get_engine().rate))
            print(f"[Jarvis] {texto}")
            self.broadcast({"type": "response", "text": texto})
            self._hud("speaking")
            tts.speak(texto)
        finally:
            self.ocupado.clear()
        self._escuchando()
        return True

    # ── Escucha (hilo) ──
    def _barge_in_activo(self, hub) -> bool:
        """Interrumpir hablando. `audio.barge_in: auto | true | false`. auto = solo con audífonos (no se oye a sí
        mismo). Con parlantes queda apagada hasta medirla en la sesión de audio: el 18/11 su propia voz por el Alaxe
        la disparaba y cortaba cada respuesta."""
        if self.barge_in == "auto":
            return hub.estado_filtro == "audífonos"
        return bool(self.barge_in)

    def run_listener(self) -> None:
        from jarvis.mic import get_hub
        from jarvis.vad import Segmenter
        hub = get_hub()
        self.hub = hub
        mq = hub.subscribe()
        seg = Segmenter(end_silence=self.fin_frase, max_seconds=8.0, preroll=0.6)   # margen tras reiniciar Silero
        silenciado = False
        voz_encima = 0          # bloques seguidos con voz mientras JARVIS habla
        traza = os.environ.get("JARVIS_TRAZA_VAD") == "1"   # solo números: bloques, prob. de voz, descartes
        tz = {"t": time.time(), "n": 0, "pmax": 0.0, "sordo": 0, "hablando": 0, "fuente": 0}
        while True:
            try:
                idx, pcm = mq.get(timeout=0.5)
            except queue.Empty:
                idx, pcm = None, None
            now = time.time()
            if traza:
                if pcm is not None:
                    tz["n"] += 1
                    tz["pmax"] = max(tz["pmax"], seg.last_prob)
                    tz["sordo"] += now < self.sordo_hasta
                    tz["hablando"] += tts.is_speaking() or now < tts.player.busy_until() + 0.35
                if now - tz["t"] >= 10:
                    print(f"[VAD] 10 s: {tz['n']} bloques · prob. máx {tz['pmax']:.2f} · sordo {tz['sordo']} · "
                          f"hablando {tz['hablando']} · estado {self.estado} · en frase {seg.in_speech}")
                    tz = {"t": now, "n": 0, "pmax": 0.0, "sordo": 0, "hablando": 0, "fuente": 0}
            if now < self.sordo_hasta:
                seg.reset()
                continue
            hablando = tts.is_speaking() or now < tts.player.busy_until() + 0.35
            bi = self._barge_in_activo(hub)
            # En espera solo cuenta el nombre y lo que suena es el pitido de cierre: se sigue escuchando (con
            # parlantes el filtro lo cancela; con audífonos no llega al micrófono).
            if hablando and not bi and self.estado != ESPERA:
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
            if pcm is None:
                pass
            else:
                seg.max_frames = int((20.0 if self.estado == CONVERSACION else 8.0) * 16000 / 512)
                antes = seg.in_speech
                utts = seg.feed(pcm, now, i0=idx)
                if seg.in_speech and not antes:
                    tts.precalentar()   # D-024: la voz lista antes de que haga falta
                # Interrupción por voz (D-021): el señor habla encima → JARVIS se calla y le escucha.
                if hablando and self.ocupado.is_set() and seg.in_speech and seg.last_prob >= self.bi_umbral:
                    voz_encima += 1
                    if voz_encima * len(pcm) / 16000 >= self.bi_min_voz:
                        print(f"[Conv] Interrumpido por voz ({voz_encima * len(pcm) / 16000 * 1000:.0f} ms de voz).")
                        self.interrumpido = True
                        self.abortar()
                        voz_encima = 0
                else:
                    voz_encima = 0
                for u in utts:
                    if self.debug:
                        print(f"[VAD] frase de {u.seconds:.1f} s ({self.estado}{', ocupado' if self.ocupado.is_set() else ''})")
                    if self.ocupado.is_set() and not bi:
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
    def _audio_stt(self, u) -> np.ndarray:
        """Audio que se transcribe: el limpio (sin el audio del PC) o el original del mismo tramo (D-021)."""
        hub = getattr(self, "hub", None)
        if (getattr(self, "stt_fuente", "limpio") == "crudo" and hub is not None and hub.filtrando
                and u.i0 is not None):
            raw = hub.tramo(u.i0, u.i0 + len(u.audio))
            if len(raw) == len(u.audio):
                return raw.astype(np.float32) / 32768
        return u.audio

    def _siguiente(self, transcribe) -> tuple:
        """(frase, texto, t_stt, hablando) de la próxima frase COMPLETA. Si lo transcrito queda a medias, espera
        `espera_incompleta` s a que el señor siga y une las partes (no le corta cuando piensa)."""
        from jarvis.vad import Utterance
        pend = None   # (frase, texto, t_stt, plazo, partes)
        while True:
            try:
                u = self.q.get(timeout=None if pend is None else max(0.0, pend[3] - time.time()))
            except queue.Empty:
                return pend[0], pend[1], pend[2], False   # nadie siguió: se atiende lo que hubo
            if u.t_start < self.sordo_hasta:   # empezó antes de cerrar (o durante la sordera): fuera
                pend = None
                continue
            hablando = self.ocupado.is_set()
            # Verificación ANTES de transcribir (D-015, apagada por defecto): una voz ajena no se transcribe.
            if self.verif is not None and not (self.exento and self.estado == CONVERSACION):
                ok, p = self.verif.es_el_senor(u.audio)
                if not ok:
                    print("[Voz] voz no reconocida")
                    continue
            self.exento = False
            t0 = time.time()
            texto = transcribe(Conversacion._audio_stt(self, u)).strip()
            t_stt = time.time() - t0
            if hablando:
                if texto:
                    return u, texto, t_stt, True
                continue
            if pend is not None:
                hueco = np.zeros(int(max(0.0, u.t_start - pend[0].t_end) * 16000), np.float32)[:16000]
                u = Utterance(np.concatenate([pend[0].audio, hueco, u.audio]), pend[0].t_start, u.t_end, u.t_emit)
                texto, t_stt, partes = (pend[1] + " " + texto).strip(), pend[2] + t_stt, pend[4] + 1
                pend = None
            else:
                partes = 1
            if not texto:
                continue
            if frase_incompleta(texto) and partes < 4:
                if self.debug:
                    print(f"[VAD] frase a medias: espero {self.espera_incompleta:.1f} s")
                pend = (u, texto, t_stt, time.time() + self.espera_incompleta, partes)
                continue
            return u, texto, t_stt, False

    def _segunda_opinion(self, u, transcribe, texto: str, t_stt: float) -> tuple:
        """En espera, sin nombre en el audio FILTRADO: se transcribe el ORIGINAL del mismo tramo. Con música fuerte el
        filtro a veces suaviza la «J» (18/11: «Y ahora estás despierto» filtrado, «Jarvis, te despiertas» original).
        Solo cuesta en frases que se iban a descartar. → (llama, resto, texto, t_stt)."""
        hub = getattr(self, "hub", None)
        if (getattr(self, "stt_fuente", "limpio") != "limpio" or hub is None or not hub.filtrando
                or u.i0 is None):
            return False, texto, texto, t_stt
        raw = hub.tramo(u.i0, u.i0 + len(u.audio))
        if len(raw) != len(u.audio):
            return False, texto, texto, t_stt
        t0 = time.time()
        t2 = transcribe(raw.astype(np.float32) / 32768).strip()
        t_stt += time.time() - t0
        llama, resto = detectar(t2)
        if llama:
            if self.debug:
                print(f"[VAD] nombre en el audio original (no en el filtrado), STT total {t_stt:.2f} s")
            return True, resto, t2, t_stt
        return False, texto, texto, t_stt

    def run_worker(self) -> None:
        from jarvis.stt import transcribe_audio
        while True:
            u, texto, t_stt, hablando = self._siguiente(transcribe_audio)
            if hablando:  # barge-in (solo con cancelación de eco)
                if self.es_parada(texto) or detectar(texto)[0]:
                    self.abortar()
                continue
            if self.estado == ESPERA:
                llama, resto = detectar(texto)
                if not llama:
                    llama, resto, texto, t_stt = self._segunda_opinion(u, transcribe_audio, texto, t_stt)
                if not llama:
                    if self.debug and self.verif is None:
                        from jarvis.nombre import parecido
                        r, pos = parecido(texto)
                        print(f"[VAD] sin nombre ({len(texto.split())} palabras, STT {t_stt:.2f} s, "
                              f"parecido a «jarvis» {r} en la palabra {pos + 1})")
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
            self._salir(con_sonido=False, sordo=True)
            return
        # Agenda: «no molestes hasta las 6», «ya la entregué», «recuérdamelo en una hora» (D-031)
        if self.agenda is not None:
            r = self.agenda.orden(resto)
            if r:
                print(f"[Jarvis] {r}")
                self.broadcast({"type": "response", "text": r})
                self._hud("speaking")
                tts.speak(r)
                return
        # Música y volumen: atajo local, sin cerebro (D-016)
        from jarvis import acciones
        r = acciones.intentar(resto)
        if r:
            texto, cerrar = r
            print(f"[Jarvis] {texto}")
            self.broadcast({"type": "response", "text": texto})
            self._hud("speaking")
            tiempos["respuesta"] = time.time() - u.t_end
            tts.speak(texto)
            print("[Tiempos] " + " · ".join(f"{k} {v:.2f}s" for k, v in tiempos.items()) + " (música)")
            if cerrar:
                self._salir(con_sonido=False, sordo=True)
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
                if self.abort_event.is_set():
                    raise Cancelado()   # corta el stream HTTP: la respuesta en curso se cancela
                marca.setdefault("primer_token", time.time() - t_brain0)
                deltas.put(d)
            try:
                resultado["r"] = self.procesar(resto, on_delta)
            except Cancelado:
                resultado["cancelado"] = True
            except Exception as e:
                if self.abort_event.is_set():
                    resultado["cancelado"] = True
                else:
                    resultado["e"] = e
            finally:
                deltas.put(None)

        threading.Thread(target=cerebro, daemon=True).start()

        def chunks():
            while True:
                try:
                    d = deltas.get(timeout=0.7)
                except queue.Empty:
                    yield tts.FLUSH  # pausa del cerebro (herramienta): decir ya lo recibido
                    continue
                if d is None or self.abort_event.is_set():
                    return
                yield d

        def primer_audio():
            marca["primer_audio"] = time.time() - u.t_end
            self._hud("speaking")

        dicho = tts.speak_stream(chunks(), on_first_audio=primer_audio)
        if self.abort_event.is_set() or resultado.get("cancelado"):
            print(f"[Jarvis] {dicho} [interrumpido]")
            self.broadcast({"type": "response", "text": (dicho + " …").strip()})
            return
        if "e" in resultado and not dicho:
            msg = resultado["e"].args[0] if resultado["e"].args else "Lo siento, algo ha fallado."
            dicho = msg if isinstance(msg, str) and msg.startswith(("No consigo", "El cerebro", "Lo siento")) else "Lo siento, algo ha fallado."
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
