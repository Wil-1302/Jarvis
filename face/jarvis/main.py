"""JARVIS face — voz + HUD. El cerebro es OpenClaw (jarvis/brain.py). Linux/Wayland.

Cambios respecto al original (PanPenek/JarvisAi), ver docs/ANALISIS_FACE.md y D-004/D-008:
- Opción A: face no ejecuta tools; OpenClaw hace todas las acciones (sin pyautogui/run_python/power_command).
- Sin Ollama ni fallback silencioso; sin historial reenviado (la sesión vive en OpenClaw).
- Sin msvcrt (Windows): teclado solo si hay terminal (F2/Esc no existen; se escribe y Enter).
- Frases en español; "proveedores" = cerebros (x-openclaw-model), sin keys ni URLs editables.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import yaml

from jarvis.brain import Brain, BrainError
from jarvis.stt import record_until_silence, transcribe_audio, set_abort_event
from jarvis.tts import speak, speak_streamed, is_speaking, stop_speaking

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

_abort = threading.Event()
set_abort_event(_abort)
_muted = threading.Event()
_event_listeners: list = []


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


def _check_abort() -> None:
    if _abort.is_set():
        raise _Aborted()


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


# ─── Cerebros (antes "providers"): solo etiqueta + modelo de OpenClaw; nada de keys ───

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


def _play_beep() -> None:
    try:
        t = np.linspace(0, 0.12, int(24000 * 0.12), endpoint=False)
        sd.play((0.3 * np.sin(2 * np.pi * 600 * t)).astype(np.float32), samplerate=24000)
        sd.wait()
    except Exception:
        pass


# ─── Pipeline ───

def handle_wake() -> None:
    _abort.clear()
    try:
        _handle_wake_inner()
    except _Aborted:
        print("[Jarvis] Cancelado.")
    except Exception as e:
        import traceback
        print(f"[ERROR] {e}")
        traceback.print_exc()
        if not _abort.is_set():
            _speak_if_unmuted("Lo siento, señor, algo ha fallado.")
    finally:
        _abort.clear()
        _broadcast({"type": "status", "message": "Listo."})
        print("[Jarvis] Esperando la palabra de activación...")


def _handle_wake_inner() -> None:
    if is_speaking():
        stop_speaking()
    print("[Jarvis] ¡Palabra de activación!")
    _broadcast({"type": "status", "message": "Escuchando..."})
    _speak_if_unmuted(_load_config().get("voz", {}).get("saludo_activacion", "¿Sí, señor?"))

    from jarvis.wake import pause_wake_mic, resume_wake_mic
    pause_wake_mic()
    time.sleep(0.15)
    try:
        audio = record_until_silence()
    finally:
        resume_wake_mic()
    _check_abort()
    print(f"[Jarvis] {len(audio) / 16000:.1f} s de audio, transcribiendo...")
    user_text = transcribe_audio(audio)
    if not user_text.strip():
        _speak_if_unmuted("No le he entendido, señor.")
        return
    print(f"[Usted] {user_text}")
    if _is_stop_command(user_text):
        abort_all()
        raise _Aborted()

    response_text = _process_request(user_text)
    _check_abort()
    print(f"[Jarvis] {response_text}")
    _broadcast({"type": "status", "message": "Hablando..."})
    _speak_streamed_if_unmuted(response_text)


def _process_request(user_text: str) -> str:
    _check_abort()
    _play_beep()
    _broadcast({"type": "user", "text": user_text})
    _broadcast({"type": "status", "message": "Pensando..."})
    try:
        response_text, backup = _brain().ask(user_text)
    except ConnectionError:
        response_text = "Señor, no consigo contactar con mi cerebro. El servicio de OpenClaw parece detenido."
    except TimeoutError:
        response_text = "Señor, el cerebro está tardando demasiado. Lo dejo aquí; puede preguntarme de nuevo."
    except BrainError as e:
        print(f"[Brain] {e}")
        response_text = "Lo siento, señor: ni el cerebro principal ni el de respaldo han respondido."
    else:
        if backup:
            _broadcast({"type": "provider_changed", "provider": "respaldo"})
    _check_abort()
    _broadcast({"type": "response", "text": response_text})
    return response_text


def _handle_typed_command(text: str) -> None:
    _abort.clear()
    print(f"[Usted] {text}")
    try:
        response = _process_request(text)
        print(f"[Jarvis] {response}")
        _speak_streamed_if_unmuted(response)
    except _Aborted:
        print("[Jarvis] Cancelado.")
    finally:
        _abort.clear()


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


def main() -> None:
    from jarvis.web import start_web_background, hud_url

    cfg = _load_config()
    print("[Jarvis] Arrancando...")
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

    _speak_if_unmuted(cfg.get("voz", {}).get("saludo_inicio", "JARVIS en línea, señor."))
    from jarvis.wake import listen_for_wake_word
    listen_for_wake_word(handle_wake)


if __name__ == "__main__":
    main()
