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
    "llamada": ["¿Señor?", "Dígame, señor.", "A su servicio.", "¿Sí, señor?", "Le escucho.", "¿En qué puedo ayudarle?"],
    "presencia": ["Para usted, siempre, señor.", "Despierto y atento, señor.", "Aquí estoy, señor. ¿Qué necesita?",
                  "Siempre en línea, señor.", "Le escucho perfectamente, señor."],
    "ayuda": ["Por supuesto, señor. ¿En qué le ayudo?", "Claro, señor. Dígame.", "Cuente conmigo, señor. ¿Qué necesita?",
              "Para eso estoy, señor. Usted dirá."],
    "saludo_manana": ["Buenos días, señor. ¿En qué le ayudo?", "Buenos días, señor. Todo en orden."],
    "saludo_tarde": ["Buenas tardes, señor. ¿Qué necesita?", "Buenas tardes, señor. Todo en orden por aquí."],
    "saludo_noche": ["Buenas noches, señor. ¿En qué le ayudo?", "Buenas noches, señor. Todo en orden por aquí."],
    "gracias": ["Un placer, señor.", "A su disposición.", "Siempre, señor."],
    "despedida": ["A su disposición, señor.", "Aquí estaré, señor.", "Cuando me necesite, señor.", "Entendido. Quedo en espera."],
    "no_entendi": ["Disculpe, señor, no le he entendido.", "Perdone, ¿podría repetirlo?"],
}

# Frase "vacía" (solo llamar): se contesta en local. Si trae contenido real, va al cerebro.
_PATRONES = [
    ("presencia", r"^(estas|sigues)? ?(despierto|ahi|alli|aqui|conectado|en linea|activo|vivo|por ahi)$|^me (oyes|escuchas)$|^estas (despierto|ahi|conmigo|listo)$"),
    ("ayuda", r"^(necesito|quiero|puedes|podrias)? ?(que me ayudes|tu ayuda|ayuda|ayudarme)( por favor| un momento| con algo)?$|^ayudame( con algo| por favor)?$|^tengo una (pregunta|duda|consulta)$|^te necesito$"),
    ("saludo", r"^(hola|buenas|buenos dias|buenas tardes|buenas noches|que tal|hola que tal|como estas|hola como estas|que hay)$"),
    ("gracias", r"^(gracias|muchas gracias|genial gracias|perfecto gracias)$"),
]
_DESPEDIDA = re.compile(r"(gracias,? )?(eso es todo|ya esta|nada mas|es todo|cierra la conversacion|termina(mos)?|"
                        r"hemos terminado|puedes descansar|hasta luego|adios|listo,? gracias|ya termine|nada,? gracias|nada mas,? gracias|eso es todo,? gracias|ya esta,? gracias)$")


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
    n = _norm(texto)
    return bool(n) and len(n.split()) <= 7 and bool(_DESPEDIDA.search(n))


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
        if a is None:
            a = self.engine.synth(texto)
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
