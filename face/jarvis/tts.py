"""Voz de JARVIS: motor intercambiable + reproductor persistente + habla en streaming.

- Motor (`tts.engine` en config.yaml): hoy `kokoro` (CPU). La interfaz es synth(texto) → float32 mono a `rate`.
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


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            cfg = _load_config()
            kind = cfg["tts"].get("engine", "kokoro")
            if kind != "kokoro":
                raise ValueError(f"Motor de voz desconocido: {kind}")
            _engine = KokoroEngine(cfg)
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


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?…:;])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _clean(text: str) -> str:
    """Quita markdown que no se debe leer en voz alta."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def synth(text: str) -> np.ndarray:
    return get_engine().synth(_clean(text))


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
        try:
            for c in chunks:
                if player.interrupt.is_set():
                    break
                full.append(c)
                buf += c
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
