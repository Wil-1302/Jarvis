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


# Verbo de "poner música". Puede ir precedido de relleno ("ahora", "oye", "¿puedes…?") o, si la frase habla de
# música ("Ahora Spotify reproduce…", "No pidas confirmación, reproduce…"), de cualquier cosa.
_VERBO = (r"(?:pon(?:me|nos|te|le)?|poner(?:me|nos)?|pongas|reproduce(?:me)?|reproducir|reproduzcas|toca(?:me)?|tocar|"
          r"toques|quiero (?:escuchar|oir)|pon a sonar)")
# Sin pista de música solo valen los verbos de siempre ("ponte las pilas" no es una orden de música).
_BASICO = r"(?:pon(?:me|nos|le)?|reproduce(?:me)?|toca(?:me)?|quiero (?:escuchar|oir)|pon a sonar)"
_PLAY = re.compile(rf"^(?:por favor )?{_BASICO}\s+(?P<resto>.+)$")
_VERBO_EN = re.compile(rf"\b{_VERBO}\b(?:\s+(?P<resto>.+))?$")
_RELLENO = {"ahora", "oye", "ya", "bueno", "a", "ver", "y", "entonces", "por", "favor", "jarvis", "puedes", "podrias",
            "me", "nos", "quiero", "que", "porfa", "vale", "venga", "anda", "hey", "ok", "okay", "pues", "tu"}
_PISTA_MUSICA = re.compile(r"\b(?:spotify|musica|musicas|cancion|canciones|tema|temas|playlist|disco|album)\b")
# Lo que queda tras el verbo y no dice qué poner: se mira la cláusula siguiente.
_VACIO = re.compile(r"^(?:(?:una?s? |algo de |un poco de )?(?:la )?(?:musicas?|canciones|cancion)|algo)?$")
# "unas músicas para sufrir", "canciones tristes", "música tipo lo-fi": búsqueda libre (suele salir una lista).
_ANIMO = re.compile(r"^(?:unas? |algo de |alguna |algunas )?(?:musicas?|canciones|temas|cancion|tema)\s+(?P<q>(?!de ).+)$")
_NO_MUSICA = re.compile(r"^(?:una? |el |la |los |las |mi )?(?:alarma|recordatorio|temporizador|cronometro|brillo|pantalla|"
                        r"modo|mensaje|nota|cita|evento|reunion|wifi|bluetooth|luz|luces|documento|archivo|correo|"
                        r"calculadora|navegador|chrome|terminal|pagina|video|youtube|pelicula|serie|tele|television|"
                        r"camara|foto|captura|ventana|fondo|serio|seria|comodo|al dia|a trabajar|en marcha)\b")
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


def _limpiar(resto: str) -> str:
    resto = re.sub(r"\b(?:en|de|desde) spotify\b|\bspotify\b|\bpor favor\b|\bporfa\b", " ", resto)
    return re.sub(r"\s+", " ", resto).strip()


def _resto_de_musica(texto: str, t: str) -> str | None:
    """Lo que hay que poner, o None si la frase no es una orden de poner música.

    Se recorre la frase por cláusulas (comas, puntos…): el verbo puede ir tras relleno ("ahora pon…") o tras
    cualquier cosa si la frase habla de música; si tras el verbo no queda nada útil ("reproduce música en
    Spotify, Dueles de Jesse & Joy") se usa la cláusula siguiente."""
    m = _PLAY.match(t)
    if m and not _PISTA_MUSICA.search(t):
        return _limpiar(m.group("resto")) or None  # forma de siempre: "pon X" (lo valida _NO_MUSICA después)
    hay_pista = bool(_PISTA_MUSICA.search(t))
    clausulas = [c for c in (_norm(x) for x in re.split(r"[,.;:!?¿¡]+", texto)) if c]
    for i, cl in enumerate(clausulas):
        m = _VERBO_EN.search(cl)
        if not m:
            continue
        previo = cl[:m.start()].split()
        if "no" in previo[-3:]:
            return None  # "no me pongas música"
        if not hay_pista and (not re.match(_BASICO + r"\b", cl[m.start():]) or not all(w in _RELLENO for w in previo)):
            continue
        resto = _limpiar(m.group("resto") or "")
        siguientes = [_limpiar(c) for c in clausulas[i + 1:]]
        if _VACIO.match(resto):
            util = next((c for c in siguientes if c and not _VACIO.match(c)), None)
            if util:
                return util
        return resto or "musica"  # "pon Spotify" → reanudar
    return None


def intentar(texto: str) -> tuple[str, bool] | None:
    """Si `texto` es una orden de música/volumen, la ejecuta y devuelve (respuesta, cerrar_conversacion)."""
    t = _norm(texto)
    if not t:
        return None
    spotify.olvidar_fallo()
    for accion, pat in _CONTROL:
        if pat.match(t):
            if not spotify.control(accion):
                return spotify.motivo or "No consigo controlar Spotify.", False
            return {"pause": "Pausado.", "play": "Reanudo la música.", "next": "Siguiente.",
                    "previous": "Anterior."}[accion], accion != "pause"
    m = _VOL.match(t) or _VOL2.match(t)
    sube_baja = m and m.groupdict().get("verbo", "pon")[:3] in ("sub", "baj")
    # "pon Spotify" no es volumen: con "pon/deja" hace falta "volumen" o un número.
    if m and ("volumen" in t or m.group("n") or (sube_baja and m.group("obj"))):
        return _volumen(m.groupdict().get("verbo", "pon"), m.group("obj") or "", m.group("n"))
    resto = _resto_de_musica(texto, t)
    if resto is None:
        return None
    if _NO_MUSICA.match(resto):
        return None  # "pon una alarma…", "pon el brillo…": no es música → cerebro
    if _SOLO_MUSICA.match(resto):
        return ("Reanudo la música." if spotify.control("play") else (spotify.motivo or "No consigo abrir Spotify.")), True
    a = _ARTISTA.match(resto)
    c = None if a else _CANCION_DE.match(resto)
    animo = None if a else _ANIMO.match(resto)
    try:
        if animo:
            q = re.sub(r"^(?:unas?|algo de|alguna|algunas) ", "", resto).replace("musicas", "musica")
            r = spotify.poner(cancion=q)  # búsqueda libre: "musica para sufrir" (suele salir una lista)
        elif a:
            r = spotify.poner(artista=a.group("a"))
        elif c:
            r = spotify.poner(cancion=c.group("c"), artista=c.group("a"))
        else:
            r = spotify.poner(cancion=resto)
    except Exception as e:
        print(f"[Música] Error al poner música: {e}")
        return "No consigo poner música en Spotify ahora mismo.", False
    if not r:
        return (f"No consigo poner «{resto}». {spotify.motivo}" if spotify.motivo
                else f"No consigo poner «{resto}» en Spotify."), False
    titulo, artista = r
    print(f"[Música] {titulo} — {artista}")
    return (f"Reproduciendo «{titulo}», de {artista}." if artista else f"Reproduciendo «{titulo}»."), True
