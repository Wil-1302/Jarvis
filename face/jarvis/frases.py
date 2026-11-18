"""Respuestas instantáneas: frases pregeneradas con la voz actual + sonidos cortos.

Si la frase solo llama a Jarvis ("Jarvis", "Jarvis, ¿estás despierto?", "Jarvis, necesito ayuda"),
se contesta en local sin pasar por el cerebro. Variantes sin repetir la última. El audio se genera al
arrancar (en segundo plano) y se guarda en ~/.cache/jarvis/frases/<voz>/ (fuera del repo).
"""
from __future__ import annotations

import hashlib
import os
import random
import re
import threading
import time
import unicodedata
from pathlib import Path

import numpy as np

CATEGORIAS: dict[str, list[str]] = {
    # "señor" solo de vez en cuando: repetirlo en cada frase le incomoda (2026-11-17).
    "llamada": ["¿Sí?", "Dígame.", "A su servicio.", "Le escucho.", "¿En qué puedo ayudarle?", "¿Señor?"],
    "presencia": ["Aquí estoy.", "Despierto y atento.", "Siempre en línea. ¿Qué necesita?", "Le escucho perfectamente.",
                  "Para usted, siempre, señor."],
    "ayuda": ["Por supuesto. ¿En qué le ayudo?", "Claro, dígame.", "Cuente conmigo. ¿Qué necesita?", "Usted dirá."],
    "saludo_manana": ["Buenos días. ¿En qué le ayudo?", "Buenos días, señor."],
    "saludo_tarde": ["Buenas tardes. ¿Qué necesita?", "Buenas tardes. Todo en orden por aquí."],
    "saludo_noche": ["Buenas noches. ¿En qué le ayudo?", "Buenas noches. Todo en orden por aquí."],
    "gracias": ["Un placer.", "A su disposición.", "No hay de qué."],
    "despedida": ["A su disposición.", "Aquí estaré.", "Cuando me necesite.", "Entendido. Quedo en espera.", "Hasta luego, señor."],
    "no_entendi": ["Disculpe, no le he entendido.", "Perdone, ¿podría repetirlo?"],
}

# Frase "vacía" (solo llamar): se contesta en local. Si trae contenido real, va al cerebro.
_PATRONES = [
    ("presencia", r"^(estas|sigues)? ?(despierto|ahi|alli|aqui|conectado|en linea|activo|vivo|por ahi)$|^me (oyes|escuchas)$|^estas (despierto|ahi|conmigo|listo)$"),
    ("ayuda", r"^(necesito|quiero|puedes|podrias)? ?(que me ayudes|tu ayuda|ayuda|ayudarme)( por favor| un momento| con algo)?$|^ayudame( con algo| por favor)?$|^tengo una (pregunta|duda|consulta)$|^te necesito$"),
    ("saludo", r"^(hola|buenas|buenos dias|buenas tardes|buenas noches|que tal|hola que tal|como estas|hola como estas|que hay)$"),
    ("gracias", r"^(gracias|muchas gracias|genial gracias|perfecto gracias)$"),
]
# Cierre de la conversación (D-022): la frase cierra si, quitando muletillas, SOLO quedan expresiones de cierre.
_CIERRES = sorted([
    "adios", "chao", "chau", "bye", "hasta luego", "hasta manana", "hasta pronto", "hasta la proxima", "nos vemos",
    "buenas noches", "eso es todo", "eso seria todo", "eso era todo", "es todo", "seria todo", "nada mas", "ya esta",
    "ya", "gracias", "muchas gracias", "mil gracias", "termina", "terminamos", "terminar", "termina la conversacion",
    "hemos terminado", "ya termine", "ya terminamos", "cierra", "cierra la conversacion", "cierra conversacion",
    "cerrar la conversacion", "cerrar conversacion", "fin de la conversacion", "fin", "puedes descansar", "descansa",
    "callate", "silencio", "basta", "ya basta", "para ya", "dejalo ahi", "no te quiero escuchar",
    "ya no te quiero escuchar", "puedes irte", "vete a dormir", "a dormir", "duermete", "no necesito nada mas",
    "no necesito nada", "eso nomas", "eso no mas", "nada", "ya no", "ya no gracias", "no gracias",
], key=len, reverse=True)
_MULETILLAS = sorted([
    "ok", "okay", "vale", "bueno", "bien", "muy bien", "perfecto", "listo", "genial", "de acuerdo", "entonces",
    "pues", "por favor", "por ahora", "por hoy", "por el momento", "jarvis", "senor", "y", "eso", "ahora", "entendido",
], key=len, reverse=True)
_RE_CIERRE = re.compile(r"\b(" + "|".join(map(re.escape, _CIERRES)) + r")\b")
_RE_MULETILLA = re.compile(r"\b(" + "|".join(map(re.escape, _MULETILLAS)) + r")\b")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", t)).strip()


def clasificar(resto: str) -> str | None:
    """Categoría local para el resto de la frase tras el nombre, o None si es una orden para el cerebro."""
    n = _norm(resto)
    if not n:
        return "llamada"
    for cat, pat in _PATRONES:
        if re.search(pat, n):
            return _saludo_hora() if cat == "saludo" else cat
    return None


def es_despedida(texto: str) -> bool:
    """"Adiós", "eso es todo", "ya", "gracias", "termina", "cierra la conversación, por favor", "ok, gracias,
    Jarvis"… cierran. "Gracias por la receta, ¿y el postre?" no (queda contenido)."""
    n = _norm(texto)
    if not n or len(n.split()) > 9:
        return False
    resto, k = _RE_CIERRE.subn(" ", n)
    return k > 0 and not _RE_MULETILLA.sub(" ", resto).strip()


def _saludo_hora() -> str:
    h = time.localtime().tm_hour
    return "saludo_manana" if 6 <= h < 13 else "saludo_tarde" if 13 <= h < 20 else "saludo_noche"


# ─── Sonidos ───

def _tono(freqs, dur=0.07, rate=24000, vol=0.18) -> np.ndarray:
    out = []
    for f in freqs:
        t = np.arange(int(rate * dur)) / rate
        env = np.minimum(1, t / 0.008) * np.exp(-t * 18)
        out.append((np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env)
    return (np.concatenate(out) * vol).astype(np.float32)


def sonido(nombre: str, rate: int) -> np.ndarray:
    return {"activo": _tono([880, 1320], rate=rate),      # ascendente: le escucho
            "fin": _tono([1100, 740], rate=rate, vol=0.12),  # descendente: vuelvo a espera
            }[nombre]


# ─── Caché de audio ───

class Frases:
    def __init__(self, engine):
        self.engine = engine
        self.dir = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "jarvis" / "frases" / engine.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.audio: dict[str, np.ndarray] = {}
        self.ultima: dict[str, str] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._pregenerar, name="frases", daemon=True).start()

    def _file(self, texto: str) -> Path:
        return self.dir / (hashlib.sha1(texto.encode()).hexdigest()[:16] + ".npy")

    def _get(self, texto: str) -> np.ndarray:
        with self._lock:
            if texto in self.audio:
                return self.audio[texto]
        f = self._file(texto)
        a = np.load(f) if f.exists() else None
        if a is not None:
            from jarvis.tts import recortar_silencios
            a = recortar_silencios(a, self.engine.rate)   # caché anterior a D-024: con 0,23 s de silencio delante
        if a is None:
            a = self.engine.synth(texto)
            if getattr(self.engine, "last_was_backup", False):
                return a  # salió con la voz de respaldo: no se guarda (no mezclar voces)
            np.save(f, a)
        with self._lock:
            self.audio[texto] = a
        return a

    def _pregenerar(self) -> None:
        t0 = time.time()
        for lista in CATEGORIAS.values():
            for texto in lista:
                try:
                    self._get(texto)
                except Exception as e:
                    print(f"[Frases] {texto!r}: {e}")
        print(f"[Frases] {sum(map(len, CATEGORIAS.values()))} frases listas en {time.time() - t0:.1f} s ({self.dir})")

    def elegir(self, cat: str) -> tuple[str, np.ndarray]:
        opciones = [t for t in CATEGORIAS[cat] if t != self.ultima.get(cat)] or CATEGORIAS[cat]
        texto = random.choice(opciones)
        self.ultima[cat] = texto
        return texto, self._get(texto)


# ─── ¿Frase a medias? (D-024: fin de frase adaptativo) ───
_CONECTORES = set("""y e o u ni pero que de del a al en con para por porque pues como cuando si el la los las lo un
una unos unas mi mis tu tus su sus este esta estos estas ese esa eso entonces tambien sin sobre hasta desde cual
cuales quien donde mas muy eh em ehm mmm este osea mientras aunque segun entre hacia tipo""".split())


def frase_incompleta(texto: str) -> bool:
    """True si lo transcrito parece cortado: termina en conector ("y", "pero", "de"…), en coma o en puntos
    suspensivos. Solo el nombre ("Jarvis.") NO cuenta como incompleta: se le contesta en el acto."""
    t = texto.strip()
    if not t:
        return False
    n = _norm(t)
    if not n or n in ("jarvis", "oye jarvis", "hola jarvis"):
        return False
    if t.endswith(("...", "…", ",", "-", "—")):
        return True
    return n.split()[-1] in _CONECTORES

