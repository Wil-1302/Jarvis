"""Ducking: mientras JARVIS escucha y responde, los demás sonidos bajan y después vuelven EXACTOS.

Por qué no el ducking por roles de WirePlumber: obliga a enrutar todos los streams por sinks de
loopback por rol (policy.linking.role-based), lo que cambia el grafo y la latencia de todo el
sistema. Aquí se guarda el volumen de cada stream (sink-input de pipewire-pulse), se baja al
`factor` (0,2 = 20 % del volumen que tenía) y se restaura.

Seguro ante caídas: el estado se escribe en $XDG_RUNTIME_DIR/jarvis/ducking.json ANTES de tocar nada.
`python -m jarvis.ducking restore` lo deshace; lo ejecutan el arranque de face y el ExecStopPost de
jarvis-face.service (corre también si face se cae). Siempre se restaura el volumen de antes;
las órdenes de volumen durante la conversación lo cambian con set_original().
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "jarvis"
_STATE = _DIR / "ducking.json"
_lock = threading.RLock()
_depth = 0
_factor = 0.2
_poller: threading.Thread | None = None
_stop_poll = threading.Event()


def _pactl(*args: str) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=5, check=True).stdout


def _streams() -> list[dict]:
    try:
        return json.loads(_pactl("-f", "json", "list", "sink-inputs") or "[]")
    except Exception as e:
        print(f"[Ducking] No pude listar los streams: {e}")
        return []


def _is_ours(s: dict) -> bool:
    p = s.get("properties", {})
    # pipewire-alsa no publica el PID: la voz se reconoce por el nombre que le da run.sh (PIPEWIRE_PROPS)
    return (p.get("application.process.id") == str(os.getpid()) or p.get("application.name") == "JARVIS"
            or str(p.get("node.name", "")).startswith("jarvis"))


def _vols(s: dict) -> list[int]:
    return [int(ch["value"]) for ch in s.get("volume", {}).values()]


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text())
    except Exception:
        return {}


def _save(state: dict) -> None:
    _DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = _STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(_STATE)


def _set(index: str, vols: list[int]) -> None:
    try:
        _pactl("set-sink-input-volume", index, *[str(v) for v in vols])
    except Exception as e:
        print(f"[Ducking] No pude ajustar el stream {index}: {e}")


def _duck_new() -> None:
    """Baja los streams que aún no estén bajados (incluidos los que aparezcan durante la respuesta)."""
    with _lock:
        state = _load()
        changed = []
        for s in _streams():
            idx = str(s["index"])
            if _is_ours(s) or idx in state:
                continue
            orig = _vols(s)
            if not orig:
                continue
            ducked = [max(0, round(v * _factor)) for v in orig]
            state[idx] = {"app": s.get("properties", {}).get("application.name", "?"), "orig": orig, "ducked": ducked}
            changed.append((idx, ducked))
        if changed:
            _save(state)  # primero el estado, luego el cambio
            for idx, ducked in changed:
                _set(idx, ducked)


def _poll() -> None:
    while not _stop_poll.wait(0.7):
        _duck_new()


def duck(factor: float | None = None) -> None:
    global _depth, _factor, _poller
    with _lock:
        _depth += 1
        if _depth > 1:
            return
        if factor is not None:
            _factor = factor
        _duck_new()
        _stop_poll.clear()
        _poller = threading.Thread(target=_poll, name="ducking", daemon=True)
        _poller.start()


def unduck() -> None:
    global _depth
    with _lock:
        if _depth == 0:
            return
        _depth -= 1
        if _depth > 0:
            return
        _stop_poll.set()
    if _poller:
        _poller.join(timeout=2)
    restore()


def restore() -> None:
    """Devuelve cada stream EXACTAMENTE a su volumen de antes y borra el estado. (Antes se respetaban los
    cambios hechos mientras estaba bajado, pero Spotify reajusta su volumen al cambiar de canción y la música
    se quedaba baja.) Para cambiar el volumen al que se vuelve: set_original()."""
    with _lock:
        state = _load()
        if not state:
            return
        now = {str(s["index"]): s for s in _streams()}
        for idx, rec in state.items():
            s = now.get(idx)
            if s is None or s.get("properties", {}).get("application.name", "?") != rec["app"]:
                continue  # el stream ya no existe
            _set(idx, rec["orig"])
        try:
            _STATE.unlink()
        except FileNotFoundError:
            pass


def set_original(app: str, fraccion: float) -> bool:
    """Orden de volumen durante la conversación: fija el volumen al que volverá `app` (0..1.5) y, si está
    bajado, lo deja bajado en proporción. Devuelve True si había algún stream de esa app bajado."""
    with _lock:
        state = _load()
        hit = False
        for idx, rec in state.items():
            if rec["app"].lower() == app.lower():
                v = max(0, round(65536 * fraccion))
                rec["orig"] = [v] * len(rec["orig"])
                rec["ducked"] = [max(0, round(v * _factor))] * len(rec["orig"])
                _set(idx, rec["ducked"])
                hit = True
        if hit:
            _save(state)
        return hit


def is_ducked() -> bool:
    return _depth > 0


class ducked:
    """with ducked(): ...  — baja los demás sonidos durante el bloque."""

    def __init__(self, factor: float | None = None):
        self.factor = factor

    def __enter__(self):
        try:
            duck(self.factor)
        except Exception as e:
            print(f"[Ducking] {e}")
        return self

    def __exit__(self, *exc):
        try:
            unduck()
        except Exception as e:
            print(f"[Ducking] {e}")
        return False


if __name__ == "__main__":
    if sys.argv[1:] == ["restore"]:
        restore()
    else:
        print("uso: python -m jarvis.ducking restore")
