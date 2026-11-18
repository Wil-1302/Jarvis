"""Atajos locales de música y volumen: rápidos y sin pasar por el cerebro (excepción de D-004: "medios y
volumen por latencia"; D-016). Si la frase no encaja exactamente, va al cerebro como siempre.

- Volumen "de la música" (o sin decir de qué, si Spotify está sonando) = el de SPOTIFY, no el del portátil.
  "del sistema / de la laptop / general" = salida por defecto (wpctl).
- Durante la conversación la música está bajada (ducking): la orden fija el volumen al que volverá.
- Tras una orden de música la conversación se cierra para que suene a su volumen.
"""
from __future__ import annotations

import re
import subprocess
import unicodedata

from jarvis import ducking, spotify


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ% ]+", " ", t)).strip()


_PLAY = re.compile(r"^(?:por favor )?(?:pon(?:me|nos)?|reproduce(?:me)?|toca(?:me)?|quiero (?:escuchar|oir)|"
                   r"pon a sonar|ponle)\s+(?P<resto>.+)$")
_NO_MUSICA = re.compile(r"^(?:una? |el |la |los |las |mi )?(?:alarma|recordatorio|temporizador|cronometro|brillo|pantalla|"
                        r"modo|mensaje|nota|cita|evento|reunion|wifi|bluetooth|luz|luces|documento|archivo|correo|"
                        r"calculadora|navegador|chrome|terminal|pagina|video|youtube|pelicula|serie)\b")
_SOLO_MUSICA = re.compile(r"^(?:algo de |un poco de )?(?:la )?musica(?: en spotify)?$|^spotify$|^algo$")
_ARTISTA = re.compile(r"^(?:(?:alguna|una|algo|cualquier|un tema|una cancion|una musica|musica|canciones|temas|"
                      r"cualquier cancion|algun tema|lo mejor) de )(?P<a>.+)$")
_CANCION_DE = re.compile(r"^(?:la cancion |el tema |la musica |la )?(?P<c>.+?) de (?P<a>[^ ].+)$")
_CONTROL = [
    ("pause", re.compile(r"^(?:pausa|pausar|pon pausa|para la musica|pausa la musica|"
                         r"para spotify|pausa spotify|deten la musica)$")),
    ("play", re.compile(r"^(?:continua|reanuda|sigue|dale play|play|reanuda la musica|continua la musica|"
                        r"vuelve a poner la musica|pon play)(?: en spotify| la musica)?$")),
    ("next", re.compile(r"^(?:siguiente|la siguiente|pasa|salta|cambia)(?: cancion| tema| de cancion)?$|"
                        r"^(?:pon|pasa a) la siguiente(?: cancion)?$")),
    ("previous", re.compile(r"^(?:anterior|la anterior|vuelve a la anterior|pon la anterior)(?: cancion| tema)?$")),
]
_VOL = re.compile(r"^(?P<verbo>sube|baja|pon|ponle|deja|bajale|subele)(?: un poco| mas)?(?: el)?"
                  r"(?: volumen)?(?: de| a)?(?: la| el)?(?P<obj> musica| spotify| laptop| sistema| general| portatil|"
                  r" volumen| audio)?(?: un poco| mas)?(?: (?:a|al|en) (?P<n>\d{1,3})(?: por ciento| %|%)?)?$")
_VOL2 = re.compile(r"^(?P<obj>musica|spotify|volumen|el volumen)(?: (?:a|al|en))? (?P<n>\d{1,3})(?: por ciento| %|%)?$")


def _sistema(delta: float | None = None, abs_: float | None = None) -> None:
    arg = f"{abs_:.2f}" if abs_ is not None else (f"{abs(delta):.2f}{'+' if delta > 0 else '-'}")
    subprocess.run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", arg], capture_output=True, timeout=3)


def _volumen(verbo: str, obj: str, n: str | None) -> tuple[str, bool]:
    obj = (obj or "").strip()
    sistema = obj in ("laptop", "sistema", "general", "portatil")
    if not sistema and not obj in ("musica", "spotify") and not spotify.abierto():
        sistema = True
    delta = 0.15 if verbo.startswith("sub") else -0.15 if verbo.startswith("baj") else 0.0
    if sistema:
        if n:
            _sistema(abs_=int(n) / 100)
            return f"Volumen del sistema al {int(n)} %.", False
        _sistema(delta=delta or 0.1)
        return ("Subo el volumen del sistema." if delta >= 0 else "Bajo el volumen del sistema."), False
    # Spotify
    if ducking.is_ducked():
        st = ducking._load()
        actual = next((r["orig"][0] / 65536 for r in st.values() if r["app"].lower() == "spotify"), None)
    else:
        actual = None
    actual = actual if actual is not None else (spotify.volumen() or 0.5)
    nuevo = int(n) / 100 if n else max(0.0, min(1.0, actual + (delta or 0.1)))
    if not ducking.set_original("Spotify", nuevo):
        spotify.fijar_volumen(nuevo)
    return f"Música al {round(nuevo * 100)} %.", True


def intentar(texto: str) -> tuple[str, bool] | None:
    """Si `texto` es una orden de música/volumen, la ejecuta y devuelve (respuesta, cerrar_conversacion)."""
    t = _norm(texto)
    if not t:
        return None
    for accion, pat in _CONTROL:
        if pat.match(t):
            if not spotify.control(accion):
                return "No consigo controlar Spotify.", False
            return {"pause": "Pausado.", "play": "Reanudo la música.", "next": "Siguiente.",
                    "previous": "Anterior."}[accion], accion != "pause"
    m = _VOL.match(t) or _VOL2.match(t)
    if m and ("volumen" in t or m.groupdict().get("obj") or m.groupdict().get("n")):
        return _volumen(m.groupdict().get("verbo", "pon"), m.group("obj") or "", m.group("n"))
    m = _PLAY.match(t)
    if not m:
        return None
    resto = re.sub(r"^en spotify\s+|\s+en spotify$", "", m.group("resto")).strip()
    if _NO_MUSICA.match(resto):
        return None  # "pon una alarma…", "pon el brillo…": no es música → cerebro
    if _SOLO_MUSICA.match(resto):
        return ("Reanudo la música." if spotify.control("play") else "No consigo abrir Spotify."), True
    a = _ARTISTA.match(resto)
    c = None if a else _CANCION_DE.match(resto)
    try:
        if a:
            r = spotify.buscar(artista=a.group("a"))
        elif c:
            r = spotify.buscar(cancion=c.group("c"), artista=c.group("a"))
        else:
            r = spotify.buscar(cancion=resto)
    except spotify.SinCredenciales:
        return "Para buscar canciones necesito las credenciales de Spotify; de momento solo puedo pausar, reanudar o pasar de tema.", False
    except Exception as e:
        print(f"[Música] Error de la API de Spotify: {e}")
        return "Spotify no responde ahora mismo.", False
    if not r:
        return f"No encuentro «{resto}» en Spotify.", False
    uri, titulo, artista = r
    if not spotify.reproducir(uri):
        return "No consigo abrir Spotify.", False
    print(f"[Música] {titulo} — {artista}")
    return f"Reproduciendo «{titulo}», de {artista}.", True
