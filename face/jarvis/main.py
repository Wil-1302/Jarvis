"""JARVIS face — voz + HUD. El cerebro es OpenClaw (jarvis/brain.py). Linux/Wayland.

Cambios respecto al original (PanPenek/JarvisAi), ver docs/ANALISIS_FACE.md y D-004/D-008/D-009/D-010:
- Opción A: face no ejecuta tools; OpenClaw hace todas las acciones (sin pyautogui/run_python/power_command).
- Sin Ollama ni fallback silencioso; sin historial reenviado (la sesión vive en OpenClaw).
- Activación por nombre en frases naturales (VAD + Whisper, jarvis/conversacion.py), modo conversación,
  respuestas locales pregeneradas y voz en streaming. Atajo Super+J. Sin openWakeWord.
- Teclado solo si hay terminal (se escribe y Enter).
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import yaml

from jarvis import hf_offline
hf_offline.activate()  # antes de faster-whisper/kokoro (importan huggingface_hub)

from jarvis import ducking  # noqa: E402
from jarvis.brain import Brain, BrainError  # noqa: E402
from jarvis.tts import speak, speak_streamed, stop_speaking  # noqa: E402

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

_abort = threading.Event()
_muted = threading.Event()
_event_listeners: list = []
_conv = None  # jarvis.conversacion.Conversacion


def register_event_listener(fn) -> None:
    _event_listeners.append(fn)


def _broadcast(event: dict) -> None:
    for fn in _event_listeners:
        try:
            fn(event)
        except Exception:
            pass


class _Aborted(Exception):
    pass


_FRASES_PARADA = {
    "para", "alto", "detente", "cállate", "callate", "silencio", "cancela", "cancelar",
    "jarvis para", "jarvis alto", "jarvis cancela", "olvídalo", "olvidalo", "déjalo", "dejalo",
    "stop", "jarvis stop", "cancel", "never mind", "nevermind",
}


def abort_all() -> None:
    _abort.set()
    stop_speaking()
    _broadcast({"type": "status", "message": "Detenido."})


def _is_stop_command(text: str) -> bool:
    return text.strip().lower().strip(" .,!?¡¿") in _FRASES_PARADA


def is_muted() -> bool:
    return _muted.is_set()


def toggle_mute() -> None:
    if _muted.is_set():
        _muted.clear()
    else:
        _muted.set()
        stop_speaking()
    _broadcast({"type": "mute", "muted": _muted.is_set()})
    print(f"[Jarvis] {'Silenciado' if _muted.is_set() else 'Con voz'}.")


def _speak_if_unmuted(text: str) -> None:
    if not _muted.is_set():
        speak(text)


def _speak_streamed_if_unmuted(text: str) -> None:
    if not _muted.is_set():
        speak_streamed(text)


# ─── Config ───

def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_config(cfg: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ─── Cerebros: solo etiqueta + modelo de OpenClaw; nada de keys ───

def get_providers() -> dict:
    return (_load_config().get("llm") or {}).get("brains") or {}


def get_active_provider() -> str:
    return (_load_config().get("llm") or {}).get("active_brain", "auto")


def set_active_provider(key: str) -> bool:
    cfg = _load_config()
    brains = cfg.get("llm", {}).get("brains", {})
    if key not in brains:
        return False
    cfg["llm"]["active_brain"] = key
    cfg["llm"].setdefault("openclaw", {})["model"] = brains[key].get("model") or None
    _save_config(cfg)
    _broadcast({"type": "provider_changed", "provider": key})
    return True


def _brain() -> Brain:
    def aviso(frase: str) -> None:
        print(f"[Jarvis] {frase}")
        _broadcast({"type": "status", "message": "Cerebro de respaldo"})
        _speak_if_unmuted(frase)
    return Brain.from_config(_load_config(), on_backup=aviso)


def _procesar_stream(texto: str, on_delta) -> tuple[str, bool]:
    """Orden → OpenClaw en streaming. Los errores se convierten en una frase hablada."""
    try:
        cfg = _load_config()
        b = _brain()
        if not (cfg.get("llm") or {}).get("openclaw", {}).get("model"):  # sin cerebro elegido por voz → enrutado
            from jarvis import enrutador
            m, respaldo, tipo = enrutador.elegir(texto, cfg)
            if m:
                b.model_override, b.backup_model = m, respaldo
                print(f"[Cerebro] {tipo} → {m}")
        r, backup = b.ask_stream(texto, on_delta)
        if backup:
            _broadcast({"type": "provider_changed", "provider": "respaldo"})
        return r, backup
    except ConnectionError:
        msg = "No consigo contactar con mi cerebro: el servicio de OpenClaw parece detenido."
    except TimeoutError:
        msg = "El cerebro está tardando demasiado. Lo dejo aquí; puede preguntarme de nuevo."
    except BrainError as e:
        print(f"[Brain] {e}")
        msg = "Lo siento: ni el cerebro principal ni el de respaldo han respondido."
    on_delta(msg)
    return msg, False


# ─── Órdenes escritas (HUD y terminal) ───

_agenda = None  # jarvis.agenda.Agenda


def _process_request(user_text: str) -> str:
    _broadcast({"type": "user", "text": user_text})
    if _agenda is not None:   # órdenes locales de agenda también por texto (HUD/terminal)
        r = _agenda.orden(user_text)
        if r:
            _broadcast({"type": "response", "text": r})
            return r
    _broadcast({"type": "state", "state": "thinking", "conversation": False})
    partes: list[str] = []
    r, _ = _procesar_stream(user_text, partes.append)
    _broadcast({"type": "response", "text": r})
    return r


def _handle_typed_command(text: str) -> None:
    _abort.clear()
    print(f"[Usted] {text}")
    response = _process_request(text)
    print(f"[Jarvis] {response}")
    with ducking.ducked(float((_load_config().get("audio") or {}).get("ducking", 0.2))):
        _speak_streamed_if_unmuted(response)


def _stdin_listener() -> None:
    """Solo con terminal: escribir una orden + Enter; 'para' detiene; '/mute' alterna la voz."""
    for line in sys.stdin:
        cmd = line.strip()
        if not cmd:
            continue
        if cmd == "/mute":
            toggle_mute()
        elif _is_stop_command(cmd):
            abort_all()
        else:
            _handle_typed_command(cmd)


def trigger(source: str = "atajo") -> None:
    if _conv is not None:
        _conv.trigger(source)


def main() -> None:
    import faulthandler, signal
    faulthandler.register(signal.SIGUSR1, all_threads=True)   # diagnóstico: kill -USR1 <pid> vuelca los hilos al journal
    global _conv, _agenda
    from jarvis.web import start_web_background, hud_url

    cfg = _load_config()
    print("[Jarvis] Arrancando...")
    ducking.restore()  # por si una ejecución anterior se cayó con los sonidos bajados
    from jarvis.mic import get_hub
    get_hub()  # un solo stream de micrófono (PipeWire)
    port = int(cfg.get("hud", {}).get("port", 7860))
    start_web_background(port=port)
    print(f"[Jarvis] HUD: {hud_url(port, con_token=False)} (el enlace con token se abre en el navegador)")

    if sys.stdin and sys.stdin.isatty():
        threading.Thread(target=_stdin_listener, daemon=True).start()
        print("[Jarvis] Teclado: escriba una orden y pulse Enter ('para' detiene, '/mute' silencia).")

    import os
    if cfg.get("hud", {}).get("open_browser", True) and os.environ.get("JARVIS_OPEN_BROWSER", "1") != "0":
        import webbrowser
        webbrowser.open(hud_url(port, con_token=True))

    from jarvis.stt import _get_model
    _get_model()  # Whisper cargado antes de escuchar (la 1.ª frase no paga la carga)
    from jarvis.conversacion import Conversacion
    _conv = Conversacion(procesar=_procesar_stream, broadcast=_broadcast, abortar=abort_all,
                         abort_event=_abort, es_parada=_is_stop_command)
    _conv.start()
    from jarvis.agenda import Agenda
    _agenda = Agenda(cfg.get("agenda") or {}, anunciar=lambda t, sonido=False: _conv.anunciar(t), muted=is_muted)
    _conv.agenda = _agenda
    _agenda.start()
    from jarvis.trigger import start_trigger_server
    start_trigger_server()  # atajo global (Super+J → jarvis-escucha)
    print("[Jarvis] Escuchando. Diga «Jarvis, …» o pulse Super+J.")
    threading.Event().wait()


if __name__ == "__main__":
    # Ejecutar SIEMPRE el módulo importado como jarvis.main: si no, web.py/trigger.py (que hacen
    # `from jarvis.main import …`) cargarían una segunda copia y el HUD no recibiría los eventos.
    import jarvis.main as _m
    _m.main()
