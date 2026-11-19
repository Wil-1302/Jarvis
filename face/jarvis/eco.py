"""Cancelación del audio del propio PC (D-021).

`Aec`: envoltorio ctypes de WebRTC AEC3 (native/libjarvis_aec.so, el mismo algoritmo que el módulo echo-cancel
de PipeWire). Referencia = lo que suena por la salida por defecto (su monitor); micrófono = lo captado.
Trabaja a 16 kHz mono en tramas de 10 ms (160 muestras).
"""
from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np

RATE = 16000
TRAMA = 160  # 10 ms
_LIB = Path(__file__).resolve().parent.parent / "native" / "libjarvis_aec.so"
_lib = None


def disponible() -> bool:
    return _LIB.exists()


def _cargar():
    global _lib
    if _lib is None:
        _lib = ctypes.CDLL(str(_LIB))
        _lib.jaec_new.restype = ctypes.c_void_p
        _lib.jaec_new.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
        p16 = ctypes.POINTER(ctypes.c_int16)
        _lib.jaec_process.argtypes = [ctypes.c_void_p, p16, p16, p16, ctypes.c_int]
        _lib.jaec_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)]
        _lib.jaec_free.argtypes = [ctypes.c_void_p]
    return _lib


class Aec:
    def __init__(self, ns: bool = False, hpf: bool = True, delay_ms: int = 60):
        self.lib = _cargar()
        self.h = self.lib.jaec_new(RATE, int(ns), int(hpf))
        self.delay_ms = delay_ms
        self._ref = np.zeros(0, np.int16)
        self._mic = np.zeros(0, np.int16)

    def proceso(self, ref: np.ndarray, mic: np.ndarray) -> np.ndarray:
        """ref y mic int16 del mismo instante (cualquier longitud, la misma). Devuelve mic sin eco (int16);
        lo que no completa una trama de 10 ms queda para la próxima llamada."""
        self._ref = np.concatenate([self._ref, ref.astype(np.int16)])
        self._mic = np.concatenate([self._mic, mic.astype(np.int16)])
        n = min(len(self._ref), len(self._mic)) // TRAMA
        out = np.empty(n * TRAMA, np.int16)
        p16 = ctypes.POINTER(ctypes.c_int16)
        for i in range(n):
            r = np.ascontiguousarray(self._ref[i * TRAMA:(i + 1) * TRAMA])
            m = np.ascontiguousarray(self._mic[i * TRAMA:(i + 1) * TRAMA])
            o = out[i * TRAMA:(i + 1) * TRAMA]
            self.lib.jaec_process(self.h, r.ctypes.data_as(p16), m.ctypes.data_as(p16),
                                  o.ctypes.data_as(p16), self.delay_ms)
        self._ref = self._ref[n * TRAMA:]
        self._mic = self._mic[n * TRAMA:]
        return out

    def stats(self) -> tuple[float, int]:
        e, d = ctypes.c_double(), ctypes.c_int()
        self.lib.jaec_stats(self.h, ctypes.byref(e), ctypes.byref(d))
        return e.value, d.value

    def __del__(self):
        try:
            if self.h:
                self.lib.jaec_free(self.h)
                self.h = None
        except Exception:
            pass


# ─── ¿Sale el audio por audífonos? Entonces no llega al micrófono y el filtro sobra (D-021 c) ───

_AURICULARES = ("headphone", "headset", "hands-free", "handsfree", "earbud", "earphone")


def salida_por_defecto() -> dict | None:
    import json
    import subprocess
    try:
        nombre = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=3).stdout.strip()
        sinks = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True,
                                          timeout=3).stdout or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return next((s for s in sinks if s.get("name") == nombre), None)


def _coincide(sink: dict, lista) -> bool:
    """¿La salida es una de la lista? Cada entrada se busca (sin mayúsculas) en el nombre visible, el nombre del nodo
    y la dirección Bluetooth: «Alaxe», «bluez_output.1F_D6…» o «1F:D6:84:33:C9:2E» valen igual."""
    p = sink.get("properties") or {}
    campos = " | ".join(str(x) for x in (sink.get("description"), p.get("device.description"), sink.get("name"),
                                          p.get("api.bluez5.address"), p.get("device.alias")) if x).lower()
    return any(str(e).strip().lower() in campos for e in (lista or ()) if str(e).strip())


def es_audifonos(sink: dict | None, parlantes=(), audifonos=()) -> bool:
    """True si la salida por defecto son audífonos (no suenan en la sala).

    Primero mandan las listas de config.yaml (`audio.parlantes` / `audio.audifonos`), porque hay parlantes Bluetooth
    que se anuncian como «headset» (p. ej. el Alaxe). Si no está en ninguna: Bluetooth de tipo auricular (o sin tipo),
    USB/jack con forma de auricular, o la toma de auriculares del portátil activa."""
    if not sink:
        return False
    if _coincide(sink, parlantes):
        return False
    if _coincide(sink, audifonos):
        return True
    p = sink.get("properties") or {}
    forma = (p.get("device.form_factor") or "").lower()
    puerto = (sink.get("active_port") or "").lower()
    if any(a in forma for a in _AURICULARES) or "headphone" in puerto or "headset" in puerto:
        return True
    bt = sink.get("name", "").startswith("bluez_output") or p.get("device.bus") == "bluetooth"
    return bt and forma in ("", "unknown")
