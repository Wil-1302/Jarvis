"""Spotify: buscar con la Web API (solo búsqueda, flujo client credentials) y reproducir en la app de
escritorio por MPRIS (playerctl open spotify:track:…). D-016.

Credenciales: SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET en ~/.config/jarvis/secrets.env (600). Se crean en
https://developer.spotify.com/dashboard (app propia; no requiere iniciar sesión de usuario para buscar).
"""
from __future__ import annotations

import base64
import random
import subprocess
import time

import httpx

from jarvis.brain import _leer_env

_token: tuple[str, float] | None = None
MARKET = "PE"


class SinCredenciales(RuntimeError):
    pass


def _tok() -> str:
    global _token
    if _token and time.time() < _token[1] - 60:
        return _token[0]
    cid, sec = _leer_env("SPOTIFY_CLIENT_ID"), _leer_env("SPOTIFY_CLIENT_SECRET")
    if not cid or not sec:
        raise SinCredenciales()
    r = httpx.post("https://accounts.spotify.com/api/token", data={"grant_type": "client_credentials"},
                   headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()}, timeout=6)
    r.raise_for_status()
    d = r.json()
    _token = (d["access_token"], time.time() + d.get("expires_in", 3600))
    return _token[0]


def _get(path: str, **params) -> dict:
    r = httpx.get(f"https://api.spotify.com/v1/{path}", params=params,
                  headers={"Authorization": f"Bearer {_tok()}"}, timeout=6)
    r.raise_for_status()
    return r.json()


def _desc(t: dict) -> tuple[str, str, str]:
    return t["uri"], t["name"], ", ".join(a["name"] for a in t["artists"][:2])


def buscar(cancion: str | None = None, artista: str | None = None) -> tuple[str, str, str] | None:
    """Devuelve (uri, título, artista). Solo artista → tema al azar entre sus más populares.
    Solo canción → el primer resultado (Spotify ordena por relevancia/popularidad)."""
    if artista and not cancion:
        arts = _get("search", q=artista, type="artist", limit=1, market=MARKET)["artists"]["items"]
        if not arts:
            return None
        top = _get(f"artists/{arts[0]['id']}/top-tracks", market=MARKET)["tracks"]
        return _desc(random.choice(top[:10])) if top else None
    q = f"track:{cancion} artist:{artista}" if artista else cancion
    items = _get("search", q=q, type="track", limit=5, market=MARKET)["tracks"]["items"]
    if not items and artista:
        items = _get("search", q=f"{cancion} {artista}", type="track", limit=5, market=MARKET)["tracks"]["items"]
    return _desc(items[0]) if items else None


def _pc(*args: str, timeout=4) -> subprocess.CompletedProcess:
    return subprocess.run(["playerctl", "--player=spotify", *args], capture_output=True, text=True, timeout=timeout)


def abierto() -> bool:
    return _pc("status").returncode == 0


def asegurar_abierto() -> bool:
    if abierto():
        return True
    # Hyprland 0.57 (config Lua): lanzar como hija del compositor, fuera de cualquier encierro.
    subprocess.run(["hyprctl", "dispatch", 'hl.dsp.exec_cmd("spotify")'], capture_output=True, timeout=4)
    for _ in range(40):
        time.sleep(0.5)
        if abierto():
            time.sleep(1.0)
            return True
    return False


def reproducir(uri: str) -> bool:
    if not asegurar_abierto():
        return False
    return _pc("open", uri).returncode == 0


def control(accion: str) -> bool:
    """play | pause | play-pause | next | previous"""
    if accion in ("play", "play-pause") and not asegurar_abierto():
        return False
    return _pc(accion).returncode == 0


def volumen() -> float | None:
    r = _pc("volume")
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def fijar_volumen(v: float) -> bool:
    return _pc("volume", f"{max(0.0, min(1.0, v)):.2f}").returncode == 0
