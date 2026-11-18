"""Voz de JARVIS: motor intercambiable + reproductor persistente + habla en streaming.

- Motor (`tts.engine`): `edge` (Jorge, con respaldo Piper), `azure` (oficial, preparado), `piper` o `kokoro`.
  La interfaz es synth(texto) → float32 mono a `rate`.
- Reproductor: UN OutputStream abierto mientras dura la conversación (sin re-arrancar el sink Bluetooth en
  cada frase, que costaba ~0,3 s y comía la primera sílaba). Se cierra al volver a espera.
- speak_stream(): recibe fragmentos de texto (del cerebro en streaming), corta oraciones, sintetiza la
  siguiente mientras suena la actual y empieza a hablar con la primera.
- busy_until(): instante en que termina de sonar lo enviado (para no escucharse a sí mismo).
"""
from __future__ import annotations

import queue
import re
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─── Motores ───

class KokoroEngine:
    rate = 24000
    _REPO_ID = "hexgrad/Kokoro-82M"

    def __init__(self, cfg: dict):
        import torch
        from huggingface_hub import hf_hub_download
        from kokoro import KModel, KPipeline
        t = cfg["tts"]
        km = KModel(repo_id=self._REPO_ID).to("cpu").eval()
        self.pipeline = KPipeline(lang_code=t.get("lang_code", "e"), repo_id=self._REPO_ID, model=km)
        self.voice = torch.load(hf_hub_download(repo_id=self._REPO_ID, filename=f"voices/{t['voice']}.pt"),
                                weights_only=True)
        self.speed = float(t.get("speed", 1.0))
        self.name = f"kokoro-{t['voice']}"

    def synth(self, text: str) -> np.ndarray:
        parts = [np.asarray(a, dtype=np.float32) for _, _, a in self.pipeline(text, voice=self.voice, speed=self.speed)
                 if a is not None]
        return np.concatenate(parts) if parts else np.zeros(0, np.float32)


def _to_rate(audio: np.ndarray, sr: int, rate: int) -> np.ndarray:
    if sr == rate or audio.size == 0:
        return audio.astype(np.float32)
    from math import gcd
    from scipy.signal import resample_poly
    g = gcd(rate, sr)
    return resample_poly(audio, rate // g, sr // g).astype(np.float32)


def _decode_mp3(data: bytes) -> tuple[np.ndarray, int]:
    import io
    import soundfile as sf
    a, sr = sf.read(io.BytesIO(data), dtype="float32")
    return (a.mean(axis=1) if a.ndim > 1 else a), sr


class PiperEngine:
    """Local (CPU, ~45 ms por oración). Respaldo de Edge/Azure."""
    rate = 24000

    def __init__(self, cfg: dict):
        import os
        from piper import PiperVoice, SynthesisConfig
        p = (cfg["tts"].get("piper") or {})
        model = os.path.expanduser(p.get("model", "~/.local/share/jarvis/piper/es_MX-claude-high.onnx"))
        self.voice = PiperVoice.load(model)
        self.cfg = SynthesisConfig(length_scale=float(p.get("length_scale", 1.1)))
        self.name = "piper-" + os.path.basename(model).removesuffix(".onnx")

    def synth(self, text: str) -> np.ndarray:
        chunks = list(self.voice.synthesize(text, syn_config=self.cfg))
        if not chunks:
            return np.zeros(0, np.float32)
        a = np.concatenate([c.audio_float_array for c in chunks])
        return _to_rate(a, chunks[0].sample_rate, self.rate)


class EdgeEngine:
    """Edge TTS (servicio NO oficial de Microsoft: el texto sale del equipo). D-012.

    Conexión WebSocket PERSISTENTE (D-024): edge_tts abre una por frase (~0,7 s de TLS + arranque); aquí se mantiene
    abierta y se reutiliza para cada frase (1.er audio 0,25–0,6 s frente a 0,95–1,3 s). `precalentar()` la abre de
    antemano (face lo llama al detectar que el señor empieza a hablar). Si el servidor la cierra, se reabre y se
    reintenta una vez."""
    rate = 24000
    FORMATO = "audio-24khz-48kbitrate-mono-mp3"

    def __init__(self, cfg: dict):
        import asyncio
        import threading as _th
        e = cfg["tts"].get("edge") or {}
        self.voice = e.get("voice", "es-MX-JorgeNeural")
        self.rate_s, self.pitch = e.get("rate", "-8%"), e.get("pitch", "-2Hz")
        self.timeout = float(e.get("timeout", 4.0))
        self.name = f"edge-{self.voice}{self.rate_s}{self.pitch}".replace("%", "").replace("+", "p")
        self._loop = asyncio.new_event_loop()
        _th.Thread(target=self._loop.run_forever, name="edge-tts", daemon=True).start()
        self._ws = self._session = None
        self._abierta_en = self._uso = 0.0
        self._lock = _th.Lock()

    def _run(self, coro, timeout):
        import asyncio
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    async def _conectar(self):
        import aiohttp
        from edge_tts.communicate import (DRM, SEC_MS_GEC_VERSION, WSS_HEADERS, WSS_URL, _SSL_CTX, connect_id,
                                          date_to_string)
        await self._cerrar()
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            f"{WSS_URL}&ConnectionId={connect_id()}&Sec-MS-GEC={DRM.generate_sec_ms_gec()}"
            f"&Sec-MS-GEC-Version={SEC_MS_GEC_VERSION}",
            compress=15, headers=DRM.headers_with_muid(WSS_HEADERS), ssl=_SSL_CTX)
        await self._ws.send_str(
            f"X-Timestamp:{date_to_string()}\r\nContent-Type:application/json; charset=utf-8\r\n"
            "Path:speech.config\r\n\r\n"
            '{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false",'
            f'"wordBoundaryEnabled":"false"}},"outputFormat":"{self.FORMATO}"}}}}}}}}\r\n')
        self._abierta_en = self._uso = time.time()

    async def _cerrar(self):
        try:
            if self._ws is not None:
                await self._ws.close()
            if self._session is not None:
                await self._session.close()
        except Exception:
            pass
        self._ws = self._session = None

    def _viva(self) -> bool:
        # El servidor corta las conexiones inactivas (~30–45 s, medido): pasados 25 s se reabre por precaución.
        return self._ws is not None and not self._ws.closed and time.time() - self._uso < 25

    def precalentar(self) -> None:
        """Abre la conexión si no hay una viva (no bloquea a quien llama)."""
        import asyncio
        if not self._viva() and not self._lock.locked():
            asyncio.run_coroutine_threadsafe(self._precalentar(), self._loop)

    async def _precalentar(self):
        if not self._viva():
            try:
                await self._conectar()
            except Exception as e:
                print(f"[Voz] Edge: no se pudo precalentar ({type(e).__name__}).")

    async def _sintetizar(self, text: str) -> bytes:
        import aiohttp
        from edge_tts.communicate import connect_id, date_to_string, mkssml, ssml_headers_plus_data
        from edge_tts.data_classes import TTSConfig
        if not self._viva():
            await self._conectar()
        cfg = TTSConfig(self.voice, self.rate_s, "+0%", self.pitch, "SentenceBoundary")
        await self._ws.send_str(ssml_headers_plus_data(connect_id(), date_to_string(), mkssml(cfg, text)))
        buf = b""
        async for m in self._ws:
            if m.type == aiohttp.WSMsgType.BINARY:
                hl = int.from_bytes(m.data[:2], "big")
                buf += m.data[hl + 2:]
            elif m.type == aiohttp.WSMsgType.TEXT:
                if "Path:turn.end" in m.data:
                    self._uso = time.time()
                    return buf
            else:
                break
        raise ConnectionError("Edge cerró la conexión")

    def synth(self, text: str) -> np.ndarray:
        with self._lock:
            try:
                data = self._run(self._sintetizar(text), self.timeout)
            except Exception:
                self._run(self._cerrar(), 2)
                data = self._run(self._sintetizar(text), self.timeout)   # un reintento con conexión nueva
        if not data:
            raise RuntimeError("Edge no devolvió audio")
        a, sr = _decode_mp3(data)
        return recortar_silencios(_to_rate(a, sr, self.rate), self.rate)


def recortar_silencios(a: np.ndarray, rate: int, inicio: float = 0.03, final: float = 0.25,
                       umbral: float = 0.01) -> np.ndarray:
    """Edge pone ~0,23 s de silencio delante y ~0,9 s detrás de cada frase: se dejan 30 ms y 250 ms (D-024)."""
    voz = np.flatnonzero(np.abs(a) > umbral)
    if len(voz) == 0:
        return a
    i = max(0, voz[0] - int(inicio * rate))
    j = min(len(a), voz[-1] + int(final * rate))
    return a[i:j]


class AzureEngine:
    """Azure Speech OFICIAL (misma voz Jorge). Preparado, sin activar: requiere AZURE_SPEECH_KEY y
    AZURE_SPEECH_REGION en ~/.config/jarvis/secrets.env (600) o en el .env del repo. D-012."""
    rate = 24000

    def __init__(self, cfg: dict):
        from jarvis.brain import _leer_env
        a = cfg["tts"].get("azure") or {}
        e = cfg["tts"].get("edge") or {}
        self.voice = a.get("voice", e.get("voice", "es-MX-JorgeNeural"))
        self.rate_s, self.pitch = a.get("rate", e.get("rate", "-8%")), a.get("pitch", e.get("pitch", "-2Hz"))
        self.timeout = float(a.get("timeout", 4.0))
        self.key, self.region = _leer_env("AZURE_SPEECH_KEY"), _leer_env("AZURE_SPEECH_REGION")
        if not self.key or not self.region:
            raise RuntimeError("Faltan AZURE_SPEECH_KEY / AZURE_SPEECH_REGION")
        self.name = f"azure-{self.voice}{self.rate_s}{self.pitch}".replace("%", "").replace("+", "p")

    def ssml(self, text: str) -> str:
        from xml.sax.saxutils import escape
        return (f'<speak version="1.0" xml:lang="es-MX"><voice name="{self.voice}">'
                f'<prosody rate="{self.rate_s}" pitch="{self.pitch}">{escape(text)}</prosody></voice></speak>')

    def synth(self, text: str) -> np.ndarray:
        import httpx
        r = httpx.post(f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1",
                       headers={"Ocp-Apim-Subscription-Key": self.key, "Content-Type": "application/ssml+xml",
                                "X-Microsoft-OutputFormat": "raw-24khz-16bit-mono-pcm", "User-Agent": "jarvis-face"},
                       content=self.ssml(text).encode(), timeout=self.timeout)
        r.raise_for_status()
        return np.frombuffer(r.content, np.int16).astype(np.float32) / 32768


class FallbackEngine:
    """Motor principal (Edge/Azure) con respaldo automático a Piper si falla o no hay internet.
    Tras un fallo usa Piper durante `cooldown` s antes de volver a intentar el principal."""
    rate = 24000

    def __init__(self, primary_factory, backup: PiperEngine, cooldown: float = 60.0):
        self.backup = backup
        self.cooldown = cooldown
        self._down_until = 0.0
        self.last_was_backup = False
        try:
            self.primary = primary_factory()
            self.name = self.primary.name
        except Exception as e:
            print(f"[Voz] El motor principal no arrancó ({e}); uso {backup.name}.")
            self.primary, self.name = None, backup.name

    def precalentar(self) -> None:
        if self.primary is not None and hasattr(self.primary, "precalentar"):
            self.primary.precalentar()

    def synth(self, text: str) -> np.ndarray:
        if self.primary is not None and time.time() >= self._down_until:
            try:
                a = self.primary.synth(text)
                if self.last_was_backup:
                    print(f"[Voz] {self.primary.name} vuelve a responder.")
                self.last_was_backup = False
                return a
            except Exception as e:
                self._down_until = time.time() + self.cooldown
                print(f"[Voz] {self.primary.name} falló ({type(e).__name__}: {e or 'sin respuesta'}); "
                      f"respaldo {self.backup.name} durante {self.cooldown:.0f} s.")
        self.last_was_backup = True
        return self.backup.synth(text)


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            cfg = _load_config()
            kind = cfg["tts"].get("engine", "kokoro")
            if kind == "kokoro":
                _engine = KokoroEngine(cfg)
            elif kind == "piper":
                _engine = PiperEngine(cfg)
            elif kind in ("edge", "azure"):
                factory = {"edge": EdgeEngine, "azure": AzureEngine}[kind]
                _engine = FallbackEngine(lambda: factory(cfg), PiperEngine(cfg),
                                         float(cfg["tts"].get("cooldown", 60)))
            else:
                raise ValueError(f"Motor de voz desconocido: {kind}")
            print(f"[Voz] Motor: {_engine.name}")
        return _engine


# ─── Reproductor ───

class Player:
    def __init__(self):
        self._stream: sd.OutputStream | None = None
        self._lock = threading.RLock()
        self._busy_until = 0.0
        self.interrupt = threading.Event()
        self.speaking = threading.Event()

    def _ensure(self, rate: int) -> sd.OutputStream:
        if self._stream is None or not self._stream.active or self._stream.samplerate != rate:
            self.close()
            self._stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32", blocksize=1024)
            self._stream.start()
        return self._stream

    def play(self, audio: np.ndarray, rate: int) -> bool:
        """Reproduce (bloqueante). Devuelve False si se interrumpió."""
        if audio.size == 0:
            return True
        with self._lock:
            st = self._ensure(rate)
            lat = float(st.latency or 0.1)
            self.speaking.set()
            try:
                for i in range(0, len(audio), 2048):
                    if self.interrupt.is_set():
                        return False
                    chunk = audio[i:i + 2048].reshape(-1, 1)
                    st.write(chunk)
                    self._busy_until = time.time() + lat + 0.05
            finally:
                self.speaking.clear()
            return True

    def drain(self) -> None:
        """Espera a que termine de sonar lo ya escrito."""
        while time.time() < self._busy_until and not self.interrupt.is_set():
            time.sleep(0.02)

    def busy_until(self) -> float:
        return self._busy_until

    def stop(self) -> None:
        self.interrupt.set()
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.abort()
                except Exception:
                    pass
                self._stream = None
        self._busy_until = 0.0

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


player = Player()


# ─── API ───

_SENT_END = re.compile(r"(.+?[.!?…:;])(\s+|$)", re.S)
FLUSH = object()  # marcador: el cerebro hizo una pausa (p. ej. usa una herramienta) → decir lo que haya


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?…:;])\s+', text)
    return [p.strip() for p in parts if p.strip()]


_MARCA_LINEA = re.compile(r"^\s*(?:(?:#{1,6}|>|[-*+•●▪]|\d{1,2}[.)])\s+)+")
_LINEA_SOLO_MARCAS = re.compile(r"^\s*(?:(?:[-*_=]\s*){3,}|\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-*:?\s*)\s*$")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+")
_URL = re.compile(r"(?:https?://|www\.)\S*[^\s.,;:!?)»]")


class FiltroProsa:
    """Convierte en prosa, al vuelo, el Markdown de línea que llega por streaming: quita viñetas, numeraciones,
    encabezados, citas, reglas y bloques de código, y cierra con punto las líneas sin puntuación final (cada
    elemento de una lista se dice como una frase). Solo retiene unos pocos caracteres al principio de cada línea
    (para reconocer la marca); el resto pasa en el acto. Lo de dentro de la línea lo limpia `_clean`."""

    _AMBIGUOS = set(" \t#>*-+•●▪0123456789.)|`_=:")

    def __init__(self):
        self.pend = ""            # principio de línea aún sin decidir
        self.inicio = True
        self.saltar = False       # línea descartada (valla de código, regla, separador de tabla)
        self.en_codigo = False
        self.ultimo = ""          # último carácter no blanco emitido en la línea actual

    def _decidir(self, final: bool) -> str:
        p, self.pend, self.inicio = self.pend, "", False
        if p.lstrip().startswith("```"):
            self.en_codigo, self.saltar = not self.en_codigo, True
            return ""
        if self.en_codigo or (final and _LINEA_SOLO_MARCAS.match(p)):
            self.saltar = True
            return ""
        if p.lstrip().startswith("|"):   # fila de tabla (llega entera): celdas separadas por comas
            return ", ".join(c.strip() for c in p.strip().strip("|").split("|") if c.strip())
        return _MARCA_LINEA.sub("", p)

    def _salida(self, t: str) -> str:
        if t.strip():
            self.ultimo = t.rstrip()[-1]
        return t

    def _fin_linea(self) -> str:
        out = ""
        if self.inicio and self.pend:
            out = self._salida(self._decidir(final=True)) if not self.saltar else ""
        cierre = ""
        if self.ultimo and self.ultimo not in ".!?…:;,":
            cierre = "."
        self.pend, self.inicio, self.saltar, self.ultimo = "", True, False, ""
        return out + cierre + " "

    def feed(self, texto: str) -> str:
        out = []
        for ch in texto:
            if ch == "\n":
                out.append(self._fin_linea())
                continue
            if self.saltar or (self.en_codigo and not self.inicio):
                continue
            if self.inicio:
                self.pend += ch
                p = self.pend.lstrip()
                if p.startswith("|") or (p and set(p) <= set("-*_= ") and len(self.pend) < 200):
                    continue   # fila de tabla o posible regla (---): se decide al acabar la línea
                if ch not in self._AMBIGUOS or len(self.pend) >= 8:
                    if (ch == "`" or "`" in self.pend) and len(self.pend.strip()) < 3:
                        continue
                    out.append(self._salida(self._decidir(final=False)))
                continue
            out.append(self._salida(ch))
        return "".join(out)

    def flush(self) -> str:
        """Lo retenido (al final o cuando el cerebro hace una pausa)."""
        if self.inicio and self.pend and not self.saltar:
            return self._salida(self._decidir(final=True))
        return ""


def prosa(texto: str) -> str:
    f = FiltroProsa()
    return f.feed(texto) + f.flush()


def _clean(text: str) -> str:
    """Quita el Markdown de dentro de la línea, URLs y emojis (lo de línea lo hace FiltroProsa)."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = _URL.sub("", text)
    text = _EMOJI.sub("", text)
    text = re.sub(r"\s*\|\s*", ", ", text.strip().strip("|"))
    text = re.sub(r"(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)|[`#>~]+", "", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def precalentar() -> None:
    """Abre de antemano la conexión del motor de voz (si la tiene). Barato si ya está abierta."""
    try:
        e = get_engine()
        if hasattr(e, "precalentar"):
            e.precalentar()
    except Exception:
        pass


def synth(text: str) -> np.ndarray:
    return get_engine().synth(_clean(prosa(text)))


def is_speaking() -> bool:
    return player.speaking.is_set() or time.time() < player.busy_until()


def stop_speaking() -> None:
    player.stop()


def play_audio(audio: np.ndarray, rate: int | None = None) -> bool:
    player.interrupt.clear()
    ok = player.play(audio, rate or get_engine().rate)
    player.drain()
    return ok


def speak(text: str) -> None:
    if not text or not text.strip():
        return
    play_audio(synth(text))


def speak_streamed(text: str) -> None:
    speak_stream(iter([text]))


def speak_stream(chunks, on_first_audio=None) -> str:
    """Habla mientras llegan los fragmentos. Devuelve el texto completo recibido."""
    player.interrupt.clear()
    eng = get_engine()
    sentences: queue.Queue = queue.Queue()
    audios: queue.Queue = queue.Queue(maxsize=3)
    full = []

    primero = [True]

    def splitter():
        buf = ""
        filtro = FiltroProsa()
        try:
            for c in chunks:
                if player.interrupt.is_set():
                    break
                if c is FLUSH:
                    buf += filtro.flush()
                    if len(buf.strip()) >= 2:
                        sentences.put(buf.strip())
                        buf = ""
                        primero[0] = False
                    continue
                full.append(c)
                buf += filtro.feed(c)
                while True:
                    m = _SENT_END.match(buf)
                    # 1.er trozo: cortar en la primera coma tras ~20 caracteres para empezar a hablar antes
                    if primero[0] and (not m or len(m.group(1)) > 60):
                        k = buf.find(",", 20)
                        if 0 < k < 90:
                            sentences.put(buf[:k + 1].strip())
                            buf = buf[k + 1:]
                            primero[0] = False
                            continue
                    if m:
                        primero[0] = False
                    # corte también por coma si la primera oración se alarga (empezar antes)
                    if not m and len(buf) > 140 and "," in buf[60:]:
                        k = buf.rfind(",", 60) + 1
                        sentences.put(buf[:k].strip())
                        buf = buf[k:]
                        continue
                    if not m:
                        break
                    s = m.group(1).strip()
                    if len(s) >= 2:
                        sentences.put(s)
                    buf = buf[m.end():]
            buf += filtro.flush()
            if buf.strip():
                sentences.put(buf.strip())
        finally:
            sentences.put(None)

    def synthesizer():
        try:
            while True:
                s = sentences.get()
                if s is None or player.interrupt.is_set():
                    break
                txt = _clean(s)
                if txt:
                    audios.put(eng.synth(txt))
        finally:
            audios.put(None)

    threading.Thread(target=splitter, daemon=True).start()
    threading.Thread(target=synthesizer, daemon=True).start()
    first = True
    while True:
        a = audios.get()
        if a is None:
            break
        if first and on_first_audio:
            on_first_audio()
        first = False
        if not player.play(a, eng.rate):
            break
    player.drain()
    return "".join(full)


def speak_to_bytes(text: str) -> bytes:
    """Compatibilidad: PCM int16 de la frase."""
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    return (np.clip(synth(text), -1, 1) * 32767).astype(np.int16).tobytes()
