"""¿La frase empieza llamando a Jarvis? Variantes de pronunciación española y muletillas iniciales.

Cuenta el nombre AL INICIO (tras "hey/oye/hola/eh...") o al FINAL de una frase corta (≤ 5 palabras):
"ayer vi una película donde salía Jarvis" no activa.
"""
from __future__ import annotations

import difflib
import re
import unicodedata

_MULETILLAS = {"hey", "hei", "ei", "ey", "oye", "oiga", "hola", "eh", "e", "a", "ah", "ok", "okay", "vale",
               "buenas", "buenos", "dias", "tardes", "noches", "y", "bueno", "mira", "che", "pues", "o", "hi"}
# j/y/h/ch/g/ll/sh/x/dj/zh/c/k + a/e + (r) + b/v + i + s/z  → jarvis, yarvis, harvis, charvis, jarbis, yervis, javis...
_PATRON = re.compile(r"^(j|y|h|ch|g|ll|sh|x|dj|zh|dy|c|k)?[aeo]r{0,2}[bv]i[sz]?e?$")
_EXTRA = {"jarvi", "jarbi", "yarvi", "jervis", "jarviz", "jarvees", "jarves", "jarvi's", "jarbes",
          "service", "charbis", "harbys", "yarbys", "jarvys", "garvis", "jaris"}
_NO = {"travis", "avis", "aviso", "bis", "vis", "es", "era", "jarra", "harvard", "javier", "chavis", "garbis", "parvis"}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ' ]+", " ", t).split()


def _es_nombre(w: str) -> bool:
    if w in _NO:
        return False
    if w in _EXTRA or _PATRON.match(w):
        return True
    return len(w) >= 5 and difflib.SequenceMatcher(None, w, "jarvis").ratio() >= 0.8


def detectar(texto: str) -> tuple[bool, str]:
    """Devuelve (llama_a_jarvis, resto_de_la_frase_sin_el_nombre)."""
    palabras = _norm(texto)
    for i, w in enumerate(palabras[:4]):
        if _es_nombre(w):
            # resto en el texto original: cortar tras la i-ésima palabra
            partes = re.split(r"(\s+)", texto.strip())
            cuenta, idx = -1, 0
            for idx, p in enumerate(partes):
                if p.strip() and _norm(p):
                    cuenta += len(_norm(p))
                if cuenta >= i:
                    break
            resto = "".join(partes[idx + 1:]).strip(" ,.;:!¡?¿-")
            return True, resto
        if w not in _MULETILLAS:
            break
    # Frase corta que TERMINA en el nombre: "hola, ¿qué tal Jarvis?", "gracias Jarvis"
    if 2 <= len(palabras) <= 5 and _es_nombre(palabras[-1]):
        resto = re.sub(r"[\s,]*\S+[\s.!?¡¿]*$", "", texto.strip()).strip(" ,")
        return True, resto
    return False, texto


if __name__ == "__main__":
    for t in ["Jarvis, ¿estás despierto?", "Oye Jarvis, ¿qué hora es?", "Yarvis, pon música.", "Harvis abre la calculadora",
              "Ayer vi una película donde salía Jarvis.", "Travis llegó tarde.", "Hola, ¿qué tal Jarvis?",
              "Charvis, necesito que me ayudes", "Jarvis.", "Buenas noches, Jarvis", "Javier, ven aquí"]:
        print(f"{t!r:45} → {detectar(t)}")


def parecido(texto: str) -> tuple[float, int]:
    """(máximo parecido con "jarvis" entre las palabras, posición). Solo para la traza; no revela el texto."""
    best, pos = 0.0, -1
    for i, w in enumerate(_norm(texto)):
        r = difflib.SequenceMatcher(None, w, "jarvis").ratio()
        if r > best:
            best, pos = r, i
    return round(best, 2), pos
