"""Avisos proactivos de Classroom, alarma del PC y modo no molestar (D-030, D-031).

face lo hace en local, sin cerebro: cada `revision_min` minutos pide al MCP «escuela» (127.0.0.1:18821) las tareas
sin entregar y, cada `alarma_revision_min`, al MCP «calendario» (127.0.0.1:18820) los eventos con alarma de JARVIS
(propiedad privada `jarvis_alarma=1`, la pone el agente al crear un recordatorio «con alarma»).

- Avisos de tareas el día anterior (≤ 24 h), 6 h antes y 2 h antes. Cada umbral se dice UNA vez por tarea.
- «ya la entregué» (tras un aviso): esas tareas no se vuelven a avisar. «recuérdamelo en una hora»: se pospone.
- Silencio: horario de noche y de clases (config.yaml → agenda.silencio) y «Jarvis, no molestes hasta las 6».
  En silencio solo hay notificación de escritorio, sin voz.
- Estado en ~/.local/state/jarvis/agenda.json (600): qué se avisó, entregadas, pospuestas y no molestar.

La lógica (umbrales, silencio, frases, órdenes) son funciones puras con `ahora` explícito → tests sin red.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

ESTADO = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "jarvis" / "agenda.json"
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_DIAS_CORTO = {"lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
CIERRE = "¿Empezamos? Estoy dispuesto a ayudarle."
_lock = threading.RLock()


# ─── Estado ───

def cargar(ruta: Path = ESTADO) -> dict:
    try:
        d = json.loads(ruta.read_text())
    except (FileNotFoundError, ValueError):
        d = {}
    for k in ("avisados", "entregadas", "pospuestas", "alarmas"):
        d.setdefault(k, {})
    d.setdefault("alarmas_pospuestas", {})
    d.setdefault("no_molestar_hasta", None)
    d.setdefault("ultimo", None)
    return d


def guardar(d: dict, ruta: Path = ESTADO) -> None:
    ruta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(tmp, ruta)


def limpiar(d: dict, ahora: datetime, dias: int = 30) -> None:
    """Olvida marcas viejas (el archivo no crece sin fin)."""
    corte = (ahora - timedelta(days=dias)).isoformat()
    for k in ("avisados", "entregadas", "alarmas"):
        d[k] = {i: t for i, t in d[k].items() if t >= corte}
    d["pospuestas"] = {i: t for i, t in d["pospuestas"].items() if t >= (ahora - timedelta(days=1)).isoformat()}


# ─── Silencio ───

def _rango(texto: str) -> tuple[int, int]:
    a, b = [x.strip() for x in texto.split("-")]
    m = lambda s: int(s.split(":")[0]) * 60 + int(s.split(":")[1] if ":" in s else 0)  # noqa: E731
    return m(a), m(b)


def _en_rango(minuto: int, r: tuple[int, int]) -> bool:
    a, b = r
    return a <= minuto < b if a <= b else (minuto >= a or minuto < b)   # cruza medianoche ("22:30-07:00")


def en_silencio(ahora: datetime, cfg: dict, estado: dict) -> str | None:
    """Motivo del silencio ('no molestar', 'noche', 'clase') o None."""
    h = estado.get("no_molestar_hasta")
    if h and ahora < datetime.fromisoformat(h):
        return "no molestar"
    s = cfg.get("silencio") or {}
    minuto = ahora.hour * 60 + ahora.minute
    if s.get("noche") and _en_rango(minuto, _rango(s["noche"])):
        return "noche"
    for c in s.get("clases") or []:
        dias = [_DIAS_CORTO[_norm(x)[:3]] for x in c.get("dias", [])]
        if ahora.weekday() in dias and _en_rango(minuto, _rango(c["horas"])):
            return "clase"
    return None


# ─── Avisos de tareas ───

def umbral(horas: float, umbrales: list[float]) -> float | None:
    """El umbral más pequeño que ya se alcanzó (24, 6, 2 → con 5 h quedan, el de 6)."""
    alcanzados = [u for u in umbrales if horas <= u]
    return min(alcanzados) if alcanzados else None


def a_avisar(tareas: list[dict], estado: dict, ahora: datetime, umbrales: list[float]) -> list[dict]:
    """Tareas que toca avisar ahora (y marca en `estado` lo avisado). Una tarea creada a 3 h de vencer recibe
    solo el aviso de 6 h, no tres seguidos. Las pospuestas vuelven cuando vence la espera."""
    salida = []
    for t in tareas:
        if not t.get("vence") or t["id"] in estado["entregadas"]:
            continue
        vence = datetime.fromisoformat(t["vence"])
        horas = (vence - ahora).total_seconds() / 3600
        if horas <= 0:
            continue   # vencida: no se insiste (sale al preguntar «¿qué tareas me faltan?»)
        pos = estado["pospuestas"].get(t["id"])
        if pos:
            if ahora < datetime.fromisoformat(pos):
                continue
            del estado["pospuestas"][t["id"]]
            salida.append(t)
            estado["avisados"][f"{t['id']}|pospuesta|{pos}"] = ahora.isoformat()
            continue
        u = umbral(horas, umbrales)
        if u is None:
            continue
        clave = f"{t['id']}|{u:g}"
        if clave in estado["avisados"]:
            continue
        for v in umbrales:   # los umbrales mayores, ya pasados, cuentan como avisados
            if v >= u:
                estado["avisados"].setdefault(f"{t['id']}|{v:g}", ahora.isoformat())
        salida.append(t)
    return salida


def cuando(dt: datetime, ahora: datetime) -> str:
    """'hoy a las 11:59 de la noche', 'mañana a las 3 de la tarde', 'el viernes 28 a las 8 de la mañana'."""
    h, m = dt.hour, dt.minute
    franja = "de la madrugada" if h < 6 else "de la mañana" if h < 12 else "de la tarde" if h < 19 else "de la noche"
    h12 = h % 12 or 12
    hora = f"{'la' if h12 == 1 else 'las'} {h12}" + (f":{m:02d}" if m else "") + f" {franja}"
    if h == 12 and m == 0:
        hora = "las 12 del mediodía"
    dias = (dt.date() - ahora.date()).days
    dia = "hoy" if dias == 0 else "mañana" if dias == 1 else "pasado mañana" if dias == 2 else \
        f"el {_DIAS[dt.weekday()]} {dt.day}"
    return f"{dia} a {hora}"


def frase_aviso(tareas: list[dict], ahora: datetime) -> str:
    partes = [f"«{t['titulo']}», de {t['curso']}, para {cuando(datetime.fromisoformat(t['vence']), ahora)}"
              for t in tareas[:5]]
    extra = f" y {len(tareas) - 5} más" if len(tareas) > 5 else ""
    inicio = "Señor, le falta esta actividad: " if len(tareas) == 1 else "Señor, le faltan estas actividades: "
    return inicio + "; ".join(partes) + extra + ". " + CIERRE


# ─── Órdenes locales ───

def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ: ]+", " ", t)).strip()


_NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
        "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20, "treinta": 30, "cuarenta": 40}


def _n(s: str) -> int | None:
    return int(s) if s.isdigit() else _NUM.get(s)


def duracion(t: str) -> timedelta | None:
    """'en una hora', 'en media hora', 'en 20 minutos', 'en hora y media', 'más tarde', 'en un rato'."""
    if re.search(r"\b(?:mas tarde|luego|despues)\b", t):
        return timedelta(hours=1)
    if re.search(r"\bun rato\b", t):
        return timedelta(minutes=30)
    if re.search(r"\bmedia hora\b", t):
        return timedelta(minutes=30)
    m = re.search(r"\b(\w+) horas? y media\b|\bhora y media\b", t)
    if m:
        return timedelta(hours=(_n(m.group(1)) if m.group(1) else 1) or 1, minutes=30)
    m = re.search(r"\b(\w+) (horas?|minutos?|min)\b", t)
    if m and _n(m.group(1)):
        n = _n(m.group(1))
        return timedelta(hours=n) if m.group(2).startswith("hora") else timedelta(minutes=n)
    return None


def hora_hasta(t: str, ahora: datetime) -> datetime | None:
    """'hasta las 6', 'hasta las 6 y media', 'hasta las 18:30', 'hasta las 7 de la mañana', 'hasta mañana'."""
    manana = bool(re.search(r"\bhasta manana\b", t))
    m = re.search(r"\bhasta (?:manana )?(?:a )?(?:las|la) (\w+)(?::(\d\d))?(?: y (media|cuarto))?(?: (de la (?:manana|tarde|noche)|del mediodia))?", t)
    if not m or _n(m.group(1)) is None:
        if manana:
            return (ahora + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
        return None
    h = _n(m.group(1))
    mi = int(m.group(2) or 0) + (30 if m.group(3) == "media" else 15 if m.group(3) == "cuarto" else 0)
    franja = m.group(4) or ""
    if h > 23 or mi > 59:
        return None
    base = ahora.replace(second=0, microsecond=0)
    if manana:
        base = base + timedelta(days=1)
        ahora = base.replace(hour=0, minute=0)
    if "tarde" in franja or "noche" in franja:
        h = 0 if (h == 12 and "noche" in franja) else (h + 12 if h < 12 else h)
        c = base.replace(hour=h % 24, minute=mi)
        return c if c > ahora else c + timedelta(days=1)
    if "manana" in franja or h > 12:
        c = base.replace(hour=h, minute=mi)
        return c if c > ahora else c + timedelta(days=1)
    # Sin franja: la próxima vez que lleguen esas horas (las 6 → 6:00 o 18:00, la que llegue antes).
    opciones = [base.replace(hour=x % 24, minute=mi) for x in (h, h + 12)]
    opciones = [c if c > ahora else c + timedelta(days=1) for c in opciones]
    return min(opciones)


_NO_MOLESTAR = re.compile(r"\b(?:no (?:me )?molestes|modo no molestar|no molestar|silencio total|no me interrumpas)\b")
_YA_MOLESTA = re.compile(r"\b(?:ya (?:puedes|me puedes) (?:molestar(?:me)?|hablar(?:me)?|avisar(?:me)?)|"
                         r"(?:quita|desactiva|apaga|termina|cancela)(?: el)? (?:modo )?no molestar)\b")
_ENTREGADA = re.compile(r"^(?:si |ya |ah |bueno |no )*(?:ya )?(?:la|lo|las|los)? ?(?:entregue|he entregado|envie|subi|"
                        r"termine|hice)\b(?: (?:la|las|esa|esas|todas?|tarea|tareas|actividad|actividades))*$")
_POSPONER = re.compile(r"\b(?:recuerdamel[oa]s?|recuerdame(?:lo)?|avisame|avisamel[oa]s?|dimelo|repitemelo)\b")


def ahora_local() -> datetime:
    return datetime.now().astimezone()


def responder(texto: str, estado: dict, ahora: datetime, reciente_min: float = 30) -> str | None:
    """Órdenes locales de agenda. Devuelve la respuesta (y modifica `estado`) o None si no es de aquí."""
    t = _norm(texto)
    if not t:
        return None
    if _YA_MOLESTA.search(t):
        estado["no_molestar_hasta"] = None
        return "Entendido, señor: vuelvo a avisarle con voz."
    if _NO_MOLESTAR.search(t):
        hasta = hora_hasta(t, ahora)
        dur = duracion(t) if not hasta else None
        hasta = hasta or (ahora + dur if dur else ahora + timedelta(hours=1))
        estado["no_molestar_hasta"] = hasta.isoformat()
        return f"Muy bien, señor. No le molestaré hasta {cuando(hasta, ahora).replace('hoy a ', '')}: solo notificaciones, sin voz."
    u = estado.get("ultimo")
    reciente = u and (ahora - datetime.fromisoformat(u["t"])).total_seconds() < reciente_min * 60
    if not reciente:
        return None
    if u["tipo"] == "tareas" and _ENTREGADA.match(t):
        for i in u["ids"]:
            estado["entregadas"][i] = ahora.isoformat()
        estado["ultimo"] = None
        return ("Perfecto, señor. Ya no se la recordaré." if len(u["ids"]) == 1
                else "Perfecto, señor. Ya no se las recordaré.")
    if _POSPONER.search(t):
        dur = duracion(t)
        if not dur:
            return None
        cuando_ = ahora + dur
        if u["tipo"] == "tareas":
            for i in u["ids"]:
                estado["pospuestas"][i] = cuando_.isoformat()
        else:   # alarma: se vuelve a sonar
            estado["alarmas_pospuestas"][u["ids"][0]] = {"t": cuando_.isoformat(), "titulo": u.get("titulo", "")}
        estado["ultimo"] = None
        return f"De acuerdo, señor. Se lo recuerdo {cuando(cuando_, ahora)}."
    return None


# ─── Alarmas del calendario personal ───

def alarmas_proximas(eventos: list[dict], estado: dict, ahora: datetime, ventana_min: float) -> list[dict]:
    """Eventos con alarma cuyo inicio cae en [ahora - 2 min, ahora + ventana] y no han sonado."""
    salida = []
    for e in eventos:
        ini = (e.get("start") or {}).get("dateTime")
        if not ini:
            continue
        dt = datetime.fromisoformat(ini.replace("Z", "+00:00")).astimezone()
        clave = f"{e['id']}|{dt.isoformat()}"
        if clave in estado["alarmas"]:
            continue
        if ahora - timedelta(minutes=2) <= dt <= ahora + timedelta(minutes=ventana_min):
            salida.append({"clave": clave, "id": e["id"], "titulo": e.get("summary") or "su recordatorio", "t": dt})
    return salida


# ─── Hilo ───

def notificar(titulo: str, cuerpo: str, urgente: bool = False) -> None:
    try:
        subprocess.run(["notify-send", "-a", "JARVIS", "-u", "critical" if urgente else "normal", "-i",
                        "appointment-soon", titulo, cuerpo], timeout=5, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[Agenda] notify-send falló: {e}")


class Agenda:
    """Hilo de avisos. `anunciar(texto)` es el gancho de voz de face (Conversacion.anunciar); `muted()` = /mute."""

    def __init__(self, cfg: dict, anunciar, muted=lambda: False) -> None:
        self.cfg = cfg or {}
        self.anunciar, self.muted = anunciar, muted
        self.umbrales = [float(x) for x in self.cfg.get("avisos_horas", [24, 6, 2])]
        self._timers: dict[str, threading.Timer] = {}
        from jarvis.mcp_cliente import CALENDARIO, ESCUELA, Cliente
        self.escuela = Cliente(ESCUELA, timeout=60)
        self.calendario = Cliente(CALENDARIO, timeout=30)
        self._ultimo_error: dict[str, str] = {}

    # Voz o, en silencio, solo notificación
    def _decir(self, titulo: str, texto: str, urgente: bool = False) -> None:
        with _lock:
            motivo = en_silencio(ahora_local(), self.cfg, cargar())
        notificar(titulo, texto, urgente)
        if motivo or self.muted():
            print(f"[Agenda] En silencio ({motivo or 'mute'}): solo notificación.")
            return
        self.anunciar(texto)

    def _error(self, fuente: str, e: Exception) -> None:
        msg = str(e)
        if self._ultimo_error.get(fuente) != msg:   # sin repetir el mismo error cada 15 min
            print(f"[Agenda] {fuente}: {msg}")
            self._ultimo_error[fuente] = msg

    def revisar_tareas(self) -> None:
        try:
            r = self.escuela.herramienta("tareas_pendientes", {"incluir_sin_fecha": False})
        except Exception as e:
            return self._error("escuela", e)
        self._ultimo_error.pop("escuela", None)
        ahora = ahora_local()
        with _lock:
            est = cargar()
            lista = a_avisar(r.get("tareas", []), est, ahora, self.umbrales)
            if lista:
                est["ultimo"] = {"t": ahora.isoformat(), "tipo": "tareas", "ids": [t["id"] for t in lista]}
            limpiar(est, ahora)
            guardar(est)
        if lista:
            print(f"[Agenda] Aviso de {len(lista)} tarea(s).")
            self._decir("Tareas pendientes", frase_aviso(lista, ahora))

    def revisar_alarmas(self) -> None:
        ahora = ahora_local()
        ventana = float(self.cfg.get("alarma_revision_min", 5)) + 1
        try:
            r = self.calendario.herramienta("list-events", {
                "calendarId": "primary", "timeMin": (ahora - timedelta(minutes=2)).isoformat(timespec="seconds"),
                "timeMax": (ahora + timedelta(minutes=ventana)).isoformat(timespec="seconds"),
                "privateExtendedProperty": ["jarvis_alarma=1"]})
            eventos = r.get("events", []) if isinstance(r, dict) else []
        except Exception as e:
            eventos = []
            self._error("calendario", e)
        with _lock:
            est = cargar()
            proximas = alarmas_proximas(eventos, est, ahora, ventana)
            for i, p in list(est.get("alarmas_pospuestas", {}).items()):   # «recuérdamelo en 10 minutos»
                t = datetime.fromisoformat(p["t"])
                if t <= ahora + timedelta(minutes=ventana):
                    proximas.append({"clave": f"{i}|pospuesta|{p['t']}", "id": i, "titulo": p["titulo"], "t": t})
                    del est["alarmas_pospuestas"][i]
                    guardar(est)
        for a in proximas:
            if a["clave"] in self._timers:
                continue
            espera = max(0.0, (a["t"] - ahora_local()).total_seconds())
            tm = threading.Timer(espera, self._sonar, args=(a,))
            tm.daemon = True
            self._timers[a["clave"]] = tm
            tm.start()
            print(f"[Agenda] Alarma programada en {espera / 60:.1f} min.")

    def _sonar(self, a: dict) -> None:
        self._timers.pop(a["clave"], None)
        with _lock:
            est = cargar()
            if a["clave"] in est["alarmas"]:
                return
            est["alarmas"][a["clave"]] = ahora_local().isoformat()
            est["ultimo"] = {"t": ahora_local().isoformat(), "tipo": "alarma", "ids": [a["id"]], "titulo": a["titulo"]}
            guardar(est)
        ignora = bool(self.cfg.get("alarma_ignora_silencio", False))
        texto = f"Señor, es la hora: {a['titulo']}."
        if ignora:
            notificar("Alarma", texto, True)
            self.anunciar(texto, sonido=True)
        else:
            self._decir("Alarma", texto, urgente=True)

    def orden(self, texto: str) -> str | None:
        """Gancho de conversacion.py: órdenes locales («no molestes hasta las 6», «ya la entregué»…)."""
        with _lock:
            est = cargar()
            r = responder(texto, est, ahora_local())
            if r:
                guardar(est)
        return r

    def _bucle(self, cada_min: float, fn, retraso: float) -> None:
        time.sleep(retraso)
        while True:
            try:
                fn()
            except Exception as e:
                print(f"[Agenda] {fn.__name__}: {e}")
            time.sleep(cada_min * 60)

    def start(self) -> None:
        if not self.cfg.get("activo", True):
            print("[Agenda] Avisos apagados (agenda.activo: false).")
            return
        threading.Thread(target=self._bucle, args=(float(self.cfg.get("revision_min", 15)), self.revisar_tareas, 30),
                         name="avisos", daemon=True).start()
        threading.Thread(target=self._bucle, args=(float(self.cfg.get("alarma_revision_min", 5)), self.revisar_alarmas, 20),
                         name="alarmas", daemon=True).start()
        print("[Agenda] Avisos de Classroom y alarmas activos.")
