"""¿Charla o trabajo? Elige el cerebro por petición (D-017, a petición del señor).

- Charla (preguntas, conversación, cuentos, consejos) → `llm.enrutado.charla` (GPT: ahorra cuota de Claude).
- Trabajo (abrir/crear/escribir/programar/documentos/archivos/búsquedas/clima/recordatorios…) o peticiones
  largas → `llm.enrutado.trabajo` (Claude Sonnet).
Medido: GPT-5.6 Terra 1.ª oración 3,1 s frente a 1,4 s de Sonnet: la charla responde ~1,7 s más tarde.
"""
from __future__ import annotations

import re
import unicodedata

_TRABAJO = re.compile(
    r"\b(abre|abrir|cierra|crea|crear|creame|escribe|escribeme|redacta|genera|haz(me)? (un|una)|programa|programar|"
    r"codigo|codifica|script|funcion|python|javascript|html|css|sql|bash|terminal|compila|depura|debug|"
    r"documento|informe|ensayo|carta formal|presentacion|diapositiva|excel|hoja de calculo|word|pdf|tabla|"
    r"archivo|archivos|carpeta|descarga|instala|configura|actualiza|"
    r"busca|buscar|investiga|averigua|consulta|tiempo hace|tiempo hara|tiempo va|clima|pronostico|noticias|precio|"
    r"cotizacion|resultado del partido|recuerdame|recordatorio|alarma|temporizador|agenda|calendario|cita|"
    r"correo|email|envia|enviale|manda|mandale|traduce|resume|resumen|analiza|calcula|"
    r"pagina|web|url|spotify|volumen|reproduce|aplicacion|app|navegador|chrome|libreoffice|pantalla|captura|"
    # Música: face la atiende en local; si una orden se le escapa, que llegue al agente completo y no a la vía
    # ligera de charla (que no tiene herramientas) — ver test de regresión.
    r"musica|musicas|cancion|canciones|playlist|album|disco|cantante|reproducir|reproduzcas|pausa|"
    r"pon(me|te|le)? (algo|una|unas|un|el|la|los|las|musica)|canva|imagen|imagenes|foto|fotos|receta)\b")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", t)).strip()


def tipo(texto: str) -> str:
    """'trabajo' o 'charla'."""
    n = _norm(texto)
    if len(n.split()) > 30 or _TRABAJO.search(n):
        return "trabajo"
    return "charla"


def elegir(texto: str, cfg: dict) -> tuple[str | None, str | None, str]:
    """(modelo, respaldo, tipo) según config. Si el enrutado está apagado → (None, None, tipo)."""
    e = ((cfg.get("llm") or {}).get("enrutado") or {})
    t = tipo(texto)
    if not e.get("activo"):
        return None, None, t
    charla, trabajo = e.get("charla"), e.get("trabajo")
    return (charla, trabajo, t) if t == "charla" else (trabajo, charla, t)
