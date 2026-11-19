"""Spotify en la app de escritorio (D-016, D-018). Dos caminos para "pon X":

1. **Escritorio (por defecto, sin credenciales):** la búsqueda rápida de la app (Ctrl+K), se pega la consulta y
   Shift+Enter reproduce el resultado elegido. Teclas con ydotool; el texto va por el portapapeles (la
   distribución del teclado es latam y `ydotool type` asume US), que se restaura después; el foco vuelve a la
   ventana anterior.
2. **Web API (opcional):** solo si hay SPOTIFY_CLIENT_ID/SECRET en ~/.config/jarvis/secrets.env. Desde febrero de
   2026 las apps en Development Mode exigen Premium al dueño, ya no tienen top tracks del artista y la búsqueda da
   como mucho 10 resultados: "música de ARTISTA" = búsqueda `artist:"X"` y tema al azar. Si la API falla (403 sin
   Premium, etc.) se pasa al escritorio y no se vuelve a intentar en esta sesión.

La reproducción final siempre es por MPRIS (playerctl).
"""
from __future__ import annotations

import base64
import json
import os
import random
import subprocess
import time
import unicodedata

import httpx

from jarvis import sesion
from jarvis.brain import _leer_env

_token: tuple[str, float] | None = None
_api_inutil = False  # tras un 401/403 (sin Premium) no se reintenta en esta sesión
MARKET = "PE"
LIMITE_BUSQUEDA = 10  # máximo de la API para apps en Development Mode (feb. 2026)

# Causa del último fallo, en una frase para decirla en voz alta (None si no se sabe o no hubo fallo).
motivo: str | None = None


def _fallo(msg: str) -> bool:
    global motivo
    motivo = msg
    print(f"[Música] {msg}")
    return False


def olvidar_fallo() -> None:
    global motivo
    motivo = None


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


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn").strip()


def buscar(cancion: str | None = None, artista: str | None = None) -> tuple[str, str, str] | None:
    """Web API. Devuelve (uri, título, artista). Solo artista → tema al azar entre los resultados de la búsqueda
    por artista (ya no hay top tracks). Solo canción → el primer resultado."""
    if artista and not cancion:
        items = _get("search", q=f'artist:"{artista}"', type="track", limit=LIMITE_BUSQUEDA, market=MARKET)["tracks"]["items"]
        suyos = [t for t in items if any(_sin_tildes(a["name"]) == _sin_tildes(artista) for a in t["artists"])]
        elegidos = suyos or items
        return _desc(random.choice(elegidos)) if elegidos else None
    q = f'track:"{cancion}" artist:"{artista}"' if artista else cancion
    items = _get("search", q=q, type="track", limit=5, market=MARKET)["tracks"]["items"]
    if not items and artista:
        items = _get("search", q=f"{cancion} {artista}", type="track", limit=5, market=MARKET)["tracks"]["items"]
    return _desc(items[0]) if items else None


# --- Escritorio: búsqueda rápida de la app + teclas (sin credenciales) -------------------------------------
# Códigos de tecla de Linux (input-event-codes.h) para ydotool.
_CTRL, _SHIFT, _ESC, _ENTER, _ABAJO, _A, _K, _V = 29, 42, 1, 28, 108, 30, 37, 47


def _tecla(*mods_y_tecla: int) -> None:
    *mods, k = mods_y_tecla
    seq = [f"{m}:1" for m in mods] + [f"{k}:1", f"{k}:0"] + [f"{m}:0" for m in reversed(mods)]
    subprocess.run(["ydotool", "key", *seq], capture_output=True, timeout=3)


def _ydotool_activo() -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", "ydotool.service"],
                          capture_output=True, timeout=3).returncode == 0


def _ydotool_listo() -> bool:
    sock = os.environ.get("YDOTOOL_SOCKET") or os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), ".ydotool_socket")
    if os.path.exists(sock) and _ydotool_activo():
        return True
    if not sesion.uinput_accesible():
        return _fallo("No tengo control del teclado: no hay permiso sobre el dispositivo de entrada virtual.")
    subprocess.run(["systemctl", "--user", "restart", "ydotool.service"], capture_output=True, timeout=5)
    for _ in range(15):
        time.sleep(0.2)
        if os.path.exists(sock) and _ydotool_activo():
            return True
    return _fallo("No tengo control del teclado: el servicio ydotool no está funcionando.")


def _ventana_activa() -> dict:
    try:
        r = subprocess.run(["hyprctl", "activewindow", "-j"], capture_output=True, text=True, timeout=3)
        return json.loads(r.stdout or "{}") or {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def _enfocar(selector: str) -> None:
    subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "{selector}" }})'], capture_output=True, timeout=3)


def _clip_guardar() -> tuple[str, bytes] | None:
    try:
        tipos = subprocess.run(["wl-paste", "--list-types"], capture_output=True, text=True, timeout=2).stdout.split()
        if not tipos:
            return None
        tipo = next((t for t in tipos if t.startswith("text/plain")), tipos[0])
        datos = subprocess.run(["wl-paste", "-n", "-t", tipo], capture_output=True, timeout=2).stdout
        return tipo, datos
    except (OSError, subprocess.SubprocessError):
        return None


def _clip_poner(datos: bytes, tipo: str = "text/plain;charset=utf-8") -> None:
    # wl-copy se queda en segundo plano sirviendo el portapapeles: sin tuberías para no esperarlo.
    subprocess.run(["wl-copy", "-t", tipo], input=datos, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


def _clip_restaurar(guardado: tuple[str, bytes] | None) -> None:
    if guardado:
        _clip_poner(guardado[1], guardado[0])
    else:
        subprocess.run(["wl-copy", "--clear"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)


def _pista() -> str:
    return _pc("metadata", "mpris:trackid").stdout.strip()


def reproducir_busqueda(consulta: str, por_artista: bool = False) -> bool:
    """Busca en la app (Ctrl+K) y reproduce: el primer resultado o, por artista, uno de sus 5 primeros temas
    (`artist:X` deja solo temas suyos). True si la app quedó sonando."""
    if not asegurar_abierto(ventana=True) or not _ydotool_listo():
        return False
    previa = _ventana_activa()
    guardado = _clip_guardar()
    antes, estado_antes = _pista(), _pc("status").stdout.strip()
    try:
        _enfocar("class:Spotify")
        time.sleep(0.3)
        if _ventana_activa().get("class", "").lower() != "spotify":
            return _fallo("No consigo poner la ventana de Spotify en primer plano.")
        _tecla(_ESC)
        _tecla(_CTRL, _K)
        time.sleep(0.7)
        _tecla(_CTRL, _A)
        _clip_poner(((f"artist:{consulta}") if por_artista else consulta).encode())
        _tecla(_CTRL, _V)
        time.sleep(1.6)  # resultados
        for _ in range(random.randint(0, 4) if por_artista else 0):
            _tecla(_ABAJO)
        _tecla(_SHIFT, _ENTER)
        time.sleep(0.4)
        _tecla(_ESC)
    finally:
        _clip_restaurar(guardado)
        if previa.get("address") and previa.get("class", "").lower() != "spotify":
            _enfocar(f"address:{previa['address']}")
    for _ in range(20):
        if _pc("status").stdout.strip() == "Playing" and (_pista() != antes or estado_antes != "Playing"):
            return True
        time.sleep(0.25)
    return _fallo("Busqué en Spotify, pero no empezó a sonar.")


def sonando() -> tuple[str, str] | None:
    r = _pc("metadata", "--format", "{{title}}\t{{artist}}")
    if r.returncode != 0 or "\t" not in r.stdout:
        return None
    t, a = r.stdout.rstrip("\n").split("\t", 1)
    return (t, a) if t else None


def poner(cancion: str | None = None, artista: str | None = None) -> tuple[str, str] | None:
    """Reproduce y devuelve (título, artista) de lo que suena; None si no se pudo. Web API si hay credenciales y
    funciona; si no, la búsqueda de la app de escritorio."""
    global _api_inutil
    if not _api_inutil:
        try:
            r = buscar(cancion=cancion, artista=artista)
            if r and reproducir(r[0]):
                return r[1], r[2]
            if r is None:
                return None
        except SinCredenciales:
            _api_inutil = True
        except httpx.HTTPStatusError as e:
            print(f"[Música] Web API de Spotify: HTTP {e.response.status_code}; uso la app de escritorio.")
            if e.response.status_code in (401, 403):
                _api_inutil = True
        except httpx.HTTPError as e:
            print(f"[Música] Web API de Spotify: {type(e).__name__}; uso la app de escritorio.")
    consulta = f"{cancion} {artista}" if cancion and artista else (cancion or artista or "")
    if not reproducir_busqueda(consulta, por_artista=bool(artista and not cancion)):
        return None
    time.sleep(0.5)
    return sonando() or (consulta, "")


def _pc(*args: str, timeout=4) -> subprocess.CompletedProcess:
    return subprocess.run(["playerctl", "--player=spotify", *args], capture_output=True, text=True, timeout=timeout)


def abierto() -> bool:
    return _pc("status").returncode == 0


def ventana_abierta() -> bool:
    """¿Hay una ventana de Spotify en Hyprland? (MPRIS aparece antes que la ventana al arrancar.)"""
    try:
        r = subprocess.run(["hyprctl", "clients", "-j"], capture_output=True, text=True, timeout=3)
        return any((c.get("class") or "").lower() == "spotify" for c in json.loads(r.stdout or "[]"))
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


ESPERA_ARRANQUE = 20.0   # s como mucho hasta que haya MPRIS y ventana
ASENTAR = 2.5            # s tras aparecer la ventana: la búsqueda rápida (Ctrl+K) aún no responde antes


def asegurar_abierto(ventana: bool = False) -> bool:
    """Spotify en marcha (MPRIS) y, si `ventana`, con su ventana visible y lista para recibir teclas.
    Si estaba cerrado lo abre y espera."""
    # Si face arrancó antes que la sesión gráfica, sin esto hyprctl/wl-copy no ven a Hyprland.
    hay_sesion = sesion.asegurar_entorno()
    if abierto() and (not ventana or ventana_abierta()):
        return True
    estaba_cerrado = not abierto()
    if not hay_sesion:
        return _fallo("Spotify no está abierto y no encuentro la sesión gráfica para abrirlo." if estaba_cerrado
                      else "No encuentro la sesión gráfica, así que no veo la ventana de Spotify.")
    if estaba_cerrado:
        print("[Música] Spotify estaba cerrado: lo abro.")
        # Hyprland 0.57 (config Lua): lanzar como hija del compositor, fuera de cualquier encierro.
        r = subprocess.run(["hyprctl", "dispatch", 'hl.dsp.exec_cmd("spotify")'], capture_output=True, text=True, timeout=4)
        if r.returncode != 0 or (r.stdout or "").strip().lower().startswith(("error", "couldn't", "invalid")):
            return _fallo("Spotify no está abierto y Hyprland no me deja abrirlo.")
    for _ in range(int(ESPERA_ARRANQUE / 0.5)):
        time.sleep(0.5)
        if abierto() and (not ventana or ventana_abierta()):
            time.sleep(ASENTAR if ventana else 1.0)
            return True
    if estaba_cerrado and not abierto():
        return _fallo("Spotify no está abierto y no terminó de arrancar a tiempo.")
    return _fallo("Spotify está abierto, pero no encuentro su ventana.")


def reproducir(uri: str) -> bool:
    if not asegurar_abierto():
        return False
    return _pc("open", uri).returncode == 0 or _fallo("Spotify no aceptó la orden de reproducir.")


def control(accion: str) -> bool:
    """play | pause | play-pause | next | previous"""
    if accion in ("play", "play-pause") and not asegurar_abierto():
        return False
    if not abierto():
        return _fallo("Spotify no está abierto.")
    return _pc(accion).returncode == 0 or _fallo("Spotify no aceptó la orden.")


def volumen() -> float | None:
    r = _pc("volume")
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def fijar_volumen(v: float) -> bool:
    return _pc("volume", f"{max(0.0, min(1.0, v)):.2f}").returncode == 0
