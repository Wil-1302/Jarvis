from __future__ import annotations
from pathlib import Path
import queue
import threading
import time
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)


# ─── Pausa durante la grabación del STT ───
# El micrófono es compartido (jarvis.mic): no hay que soltar el dispositivo, solo dejar de
# evaluar la wake word mientras el STT graba la orden.
_mic_pause = threading.Event()


def pause_wake_mic() -> None:
    _mic_pause.set()


def resume_wake_mic() -> None:
    _mic_pause.clear()


# ─── Activación (wake word o atajo de teclado) ───
_busy = threading.Lock()
_ignore_until = [0.0]
_callback = None


def trigger(source: str = "wake") -> None:
    """IDLE → lanza la escucha de una orden. BUSY → lo detiene todo (interrupción)."""
    now = time.time()
    if source == "wake" and now < _ignore_until[0]:
        return  # enfriamiento: evita que el eco de "¿Sí, señor?" vuelva a disparar
    if _busy.locked():
        _ignore_until[0] = now + 3.0
        from jarvis.main import abort_all
        abort_all()
        print(f"[Jarvis] Detenido ({source}).")
        return
    if _callback is None:
        return
    _ignore_until[0] = now + 2.0

    def _run():
        with _busy:
            _callback()

    threading.Thread(target=_run, daemon=True).start()


def listen_for_wake_word(callback) -> None:
    """Escucha la wake word para siempre (bloqueante) sobre el micrófono compartido."""
    global _callback
    _callback = callback
    from openwakeword.model import Model
    from jarvis.mic import get_hub

    cfg = _load_config()["wake_word"]
    threshold = float(cfg["threshold"])
    log_from = float(cfg.get("log_from", 0.15))
    oww = Model(wakeword_models=[cfg["model"]], inference_framework="onnx")

    hub = get_hub()
    q = hub.subscribe()
    print("[Jarvis] Listening for wake word...")
    paused = False
    best = 0.0  # mejor puntuación del episodio actual (para calibrar el umbral)
    stats_every = float(cfg.get("stats_every", 0))  # >0: resumen periódico en el journal
    stats_t, stats_max, stats_n = time.time(), 0.0, 0
    try:
        while True:
            try:
                pcm = q.get(timeout=1.0)
            except queue.Empty:
                continue
            if _mic_pause.is_set():
                paused = True
                continue
            if paused:  # vuelve tras grabar una orden: estado limpio
                paused = False
                oww.reset()
                best = 0.0
                with q.mutex:
                    q.queue.clear()
                continue

            score = float(oww.predict(pcm).get(cfg["model"], 0))
            if stats_every:
                stats_max, stats_n = max(stats_max, score), stats_n + 1
                if time.time() - stats_t >= stats_every:
                    print(f"[Wake] {stats_n} bloques, puntuación máx {stats_max:.3f}, ruido {hub.noise_floor():.4f}")
                    stats_t, stats_max, stats_n = time.time(), 0.0, 0
            if score >= log_from:
                best = max(best, score)
            elif best:
                print(f"[Wake] puntuación máx {best:.3f} (umbral {threshold})")
                best = 0.0
            if score >= threshold:
                oww.reset()
                trigger("wake")
    finally:
        hub.unsubscribe(q)
