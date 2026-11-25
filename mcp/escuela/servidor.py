#!/usr/bin/env python3
"""JARVIS — MCP «escuela»: Google Classroom y Calendar de la cuenta INSTITUCIONAL, solo lectura (D-029).

Sin dependencias fuera de la biblioteca estándar (fácil de revisar). Corre como servicio de usuario propio
(`jarvis-escuela.service`), FUERA del encierro del gateway: el token vive en ~/.config/jarvis/google/ (700), que el
gateway no puede leer. El agente solo llega a Google a través de las herramientas de este servidor.

- Scopes de solo lectura: con este token no se puede escribir nada en Google, lo use quien lo use.
- HTTP solo en 127.0.0.1, Host y Origin locales (contra DNS rebinding), cuerpo limitado.
- Los errores de Google se devuelven tal cual (código, estado y mensaje): si la institución bloquea el acceso,
  el señor ve el error exacto.

Uso:
  servidor.py login      Inicia sesión (navegador) con la cuenta institucional y guarda el token (600).
  servidor.py check      Comprueba que el token sigue valiendo (para doctor.sh). Salida: OK/ERROR, sin secretos.
  servidor.py tareas     Imprime las tareas sin entregar (prueba por terminal).
  servidor.py serve      Servidor MCP (Streamable HTTP, JSON) en 127.0.0.1:18821/mcp. Es lo que hace el servicio.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import socketserver
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DIR = Path(os.environ.get("JARVIS_GOOGLE_DIR", Path.home() / ".config/jarvis/google"))
CLIENTE = DIR / "oauth-client.json"
TOKEN = DIR / "escuela-token.json"
HOST, PUERTO = "127.0.0.1", int(os.environ.get("JARVIS_ESCUELA_PORT", "18821"))
SCOPES = [
    "openid", "email",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CLASSROOM = "https://classroom.googleapis.com/v1"
CALENDAR = "https://www.googleapis.com/calendar/v3"
PENDIENTE = {"NEW", "CREATED", "RECLAIMED_BY_STUDENT"}   # sin entregar; TURNED_IN / RETURNED = entregada
VERSION = "1.0.1"
# Google concede `classroom.student-submissions.me.readonly` como alias de `classroom.coursework.me.readonly` (son el
# mismo permiso: probado el 24/11/2026, courseWork.list y studentSubmissions.list userId=me responden con él). Un scope
# pedido se da por concedido si llega él o cualquiera de sus equivalentes.
EQUIVALENTES = {
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly": {
        "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly"},
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly": {
        "https://www.googleapis.com/auth/classroom.coursework.me.readonly"},
}


class GoogleError(Exception):
    """Error de Google con su texto exacto (código HTTP, estado y mensaje)."""


# ─── Credenciales ───

def _cliente() -> dict:
    try:
        d = json.loads(CLIENTE.read_text())
    except FileNotFoundError:
        raise GoogleError(f"Falta el cliente OAuth: {CLIENTE} (ver mcp/escuela.md)") from None
    c = d.get("installed") or d.get("web") or {}
    if not c.get("client_id") or not c.get("client_secret"):
        raise GoogleError(f"{CLIENTE} no es un cliente OAuth de tipo «Escritorio»")
    return c


def _guardar(datos: dict) -> None:
    DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = TOKEN.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(datos, f)
    os.replace(tmp, TOKEN)


def _post_form(url: str, campos: dict) -> dict:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(campos).encode(), method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise GoogleError(_texto_error(e)) from None


def _texto_error(e: urllib.error.HTTPError) -> str:
    cuerpo = e.read().decode("utf-8", "replace")
    try:
        j = json.loads(cuerpo)
        err = j.get("error")
        if isinstance(err, dict):
            razones = ",".join(x.get("reason", "") for x in err.get("details", []) if isinstance(x, dict) and x.get("reason"))
            return f"HTTP {e.code} {err.get('status', '')}: {err.get('message', '')}" + (f" [{razones}]" if razones else "")
        return f"HTTP {e.code} {err}: {j.get('error_description', '')}".strip()
    except ValueError:
        return f"HTTP {e.code}: {cuerpo[:300]}"


class Credenciales:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._acceso: str | None = None
        self._caduca = 0.0

    def token(self) -> str:
        with self._lock:
            if self._acceso and time.time() < self._caduca - 60:
                return self._acceso
            try:
                guardado = json.loads(TOKEN.read_text())
            except FileNotFoundError:
                raise GoogleError("Sin sesión de la cuenta institucional: ejecute `scripts/jarvis-google login escuela`") from None
            c = _cliente()
            r = _post_form(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                                       "refresh_token": guardado["refresh_token"], "grant_type": "refresh_token"})
            self._acceso, self._caduca = r["access_token"], time.time() + int(r.get("expires_in", 3600))
            return self._acceso


CRED = Credenciales()


def _get(url: str, params: dict | None = None) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {CRED.token()}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise GoogleError(_texto_error(e)) from None
    except urllib.error.URLError as e:
        raise GoogleError(f"Sin conexión con Google: {e.reason}") from None


def _paginas(url: str, params: dict, clave: str):
    params = dict(params)
    while True:
        r = _get(url, params)
        yield from r.get(clave, [])
        if not r.get("nextPageToken"):
            return
        params["pageToken"] = r["nextPageToken"]


# ─── Classroom ───

_cache: dict = {}


def cursos() -> list[dict]:
    """Cursos activos en los que el señor es alumno (caché de 30 min: cambian poco)."""
    c = _cache.get("cursos")
    if c and time.time() - c[0] < 1800:
        return c[1]
    lista = [{"id": x["id"], "nombre": x.get("name", ""), "seccion": x.get("section", ""), "enlace": x.get("alternateLink", "")}
             for x in _paginas(f"{CLASSROOM}/courses", {"studentId": "me", "courseStates": "ACTIVE", "pageSize": 100}, "courses")]
    _cache["cursos"] = (time.time(), lista)
    return lista


def _vencimiento(cw: dict) -> datetime | None:
    """dueDate/dueTime de Classroom están en UTC. Sin hora → fin del día (23:59 hora local)."""
    d = cw.get("dueDate")
    if not d:
        return None
    t = cw.get("dueTime")
    if t is None:
        return datetime(d["year"], d["month"], d["day"], 23, 59).astimezone()
    return datetime(d["year"], d["month"], d["day"], t.get("hours", 0), t.get("minutes", 0),
                    tzinfo=timezone.utc).astimezone()


DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre")


def fecha_dicha(d: datetime) -> str:
    """«viernes 27 de noviembre, 23:59»: el día de la semana va calculado (el modelo lo calcula mal)."""
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}, {d:%H:%M}"


def tareas_pendientes(curso_trabajo, entregas, lista_cursos, ahora: datetime | None = None,
                      incluir_sin_fecha: bool = True, dias_atras: int = 14) -> list[dict]:
    """Cálculo puro (testeable): tareas con entrega propia sin entregar, ordenadas por vencimiento.

    curso_trabajo(curso_id) → lista de courseWork; entregas(curso_id) → lista de studentSubmissions (userId=me).
    Las vencidas hace más de `dias_atras` días se omiten (Classroom acumula restos de cursos viejos)."""
    ahora = ahora or datetime.now().astimezone()
    salida = []
    for c in lista_cursos:
        por_tarea = {s["courseWorkId"]: s for s in entregas(c["id"])}
        for cw in curso_trabajo(c["id"]):
            s = por_tarea.get(cw["id"])
            if not s or s.get("state") not in PENDIENTE:
                continue   # entregada, devuelta o no asignada al señor
            vence = _vencimiento(cw)
            if vence is None and not incluir_sin_fecha:
                continue
            if vence is not None and vence < ahora - timedelta(days=dias_atras):
                continue
            salida.append({
                "id": f"{c['id']}/{cw['id']}", "curso": c["nombre"], "titulo": cw.get("title", ""),
                "vence": vence.isoformat(timespec="minutes") if vence else None,
                "vence_dicho": fecha_dicha(vence) if vence else None,
                "horas_restantes": round((vence - ahora).total_seconds() / 3600, 1) if vence else None,
                "atrasada": bool(vence and vence < ahora) or bool(s.get("late")),
                "estado": s.get("state"), "tipo": cw.get("workType", ""), "enlace": cw.get("alternateLink", ""),
            })
    salida.sort(key=lambda x: (x["vence"] is None, x["vence"] or ""))
    return salida


def _curso_trabajo(curso_id: str) -> list[dict]:
    return list(_paginas(f"{CLASSROOM}/courses/{curso_id}/courseWork",
                         {"courseWorkStates": "PUBLISHED", "pageSize": 100}, "courseWork"))


def _entregas(curso_id: str) -> list[dict]:
    return list(_paginas(f"{CLASSROOM}/courses/{curso_id}/courseWork/-/studentSubmissions",
                         {"userId": "me", "pageSize": 100}, "studentSubmissions"))


def tareas(incluir_sin_fecha: bool = True) -> list[dict]:
    return tareas_pendientes(_curso_trabajo, _entregas, cursos(), incluir_sin_fecha=incluir_sin_fecha)


def eventos(desde: str | None = None, hasta: str | None = None, maximo: int = 50) -> list[dict]:
    ahora = datetime.now().astimezone()
    desde = desde or ahora.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    hasta = hasta or (ahora + timedelta(days=7)).isoformat()
    r = _get(f"{CALENDAR}/calendars/primary/events", {"timeMin": _rfc3339(desde), "timeMax": _rfc3339(hasta),
             "singleEvents": "true", "orderBy": "startTime", "maxResults": min(int(maximo), 250)})
    return [{"titulo": e.get("summary", "(sin título)"), "inicio": (e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"),
             "fin": (e.get("end") or {}).get("dateTime") or (e.get("end") or {}).get("date"), "lugar": e.get("location", "")}
            for e in r.get("items", [])]


def _rfc3339(s: str) -> str:
    """Acepta '2026-11-25', '2026-11-25T10:00' o con zona; devuelve RFC 3339 con zona local si falta."""
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.astimezone()
    return d.isoformat()


# ─── MCP (Streamable HTTP, respuestas JSON) ───

HERRAMIENTAS = [
    {"name": "tareas_pendientes",
     "description": "Tareas de Google Classroom (cuenta institucional) que el señor AÚN NO HA ENTREGADO, por curso, "
                    "ordenadas por fecha de entrega (hora local de Lima). Solo lectura.",
     "inputSchema": {"type": "object", "properties": {
         "incluir_sin_fecha": {"type": "boolean", "description": "Incluir tareas sin fecha de entrega (por defecto sí)"}},
         "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "cursos", "description": "Cursos activos de Classroom del señor (cuenta institucional). Solo lectura.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
    {"name": "eventos_institucionales",
     "description": "Eventos del calendario de la cuenta INSTITUCIONAL (clases, exámenes…). Solo lectura: para crear "
                    "recordatorios use el calendario personal. Fechas ISO; por defecto, de hoy a 7 días.",
     "inputSchema": {"type": "object", "properties": {
         "desde": {"type": "string", "description": "Inicio, ISO 8601 (p. ej. 2026-11-25 o 2026-11-25T08:00)"},
         "hasta": {"type": "string", "description": "Fin, ISO 8601"},
         "maximo": {"type": "integer", "minimum": 1, "maximum": 250}}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": True}},
]
PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def llamar(nombre: str, args: dict) -> dict:
    try:
        if nombre == "tareas_pendientes":
            datos = {"tareas": tareas(bool(args.get("incluir_sin_fecha", True))),
                     "ahora": datetime.now().astimezone().isoformat(timespec="minutes"),
                     "hoy": fecha_dicha(datetime.now().astimezone())}
        elif nombre == "cursos":
            datos = {"cursos": cursos()}
        elif nombre == "eventos_institucionales":
            datos = {"eventos": eventos(args.get("desde"), args.get("hasta"), int(args.get("maximo", 50)))}
        else:
            return {"content": [{"type": "text", "text": f"Herramienta desconocida: {nombre}"}], "isError": True}
    except GoogleError as e:
        return {"content": [{"type": "text", "text": f"Error de Google: {e}"}], "isError": True}
    except (ValueError, KeyError, TypeError) as e:
        return {"content": [{"type": "text", "text": f"Argumentos no válidos: {e}"}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(datos, ensure_ascii=False)}], "structuredContent": datos}


def atender_rpc(msg: dict) -> dict | None:
    """Un mensaje JSON-RPC → respuesta (None para notificaciones)."""
    metodo, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None   # notificación (notifications/initialized…)
    p = msg.get("params") or {}
    if metodo == "initialize":
        pedido = p.get("protocolVersion")
        res = {"protocolVersion": pedido if pedido in PROTOCOLOS else PROTOCOLOS[0],
               "capabilities": {"tools": {"listChanged": False}},
               "serverInfo": {"name": "jarvis-escuela", "version": VERSION},
               "instructions": "Classroom y calendario de la cuenta institucional del señor, solo lectura."}
    elif metodo == "ping":
        res = {}
    elif metodo == "tools/list":
        res = {"tools": HERRAMIENTAS}
    elif metodo == "tools/call":
        res = llamar(p.get("name", ""), p.get("arguments") or {})
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Método no soportado: {metodo}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def _host_local(valor: str | None) -> bool:
    if not valor:
        return False
    h = urllib.parse.urlsplit(valor if "//" in valor else f"//{valor}").hostname or ""
    return h in ("127.0.0.1", "localhost", "::1")


class Manejador(http.server.BaseHTTPRequestHandler):
    server_version = "jarvis-escuela"
    sys_version = ""

    def log_message(self, fmt, *args):  # sin contenido en el journal: solo método, ruta y código
        sys.stderr.write(f"[escuela] {self.command} {self.path.split('?')[0]} {args[1] if len(args) > 1 else ''}\n")

    def _responder(self, codigo: int, cuerpo: dict | None = None) -> None:
        datos = json.dumps(cuerpo, ensure_ascii=False).encode() if cuerpo is not None else b""
        self.send_response(codigo)
        if cuerpo is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _permitido(self) -> bool:
        if not _host_local(self.headers.get("Host")):
            self._responder(403, {"error": "Host no permitido"})
            return False
        origen = self.headers.get("Origin")
        if origen and not _host_local(origen):
            self._responder(403, {"error": "Origin no permitido"})
            return False
        if self.path.split("?")[0] != "/mcp":
            self._responder(404, {"error": "no encontrado"})
            return False
        return True

    def do_GET(self):
        if self._permitido():
            self._responder(405, {"error": "solo POST (sin flujo SSE)"})

    def do_DELETE(self):
        if self._permitido():
            self._responder(405, {"error": "sin sesiones"})

    def do_POST(self):
        if not self._permitido():
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > 256 * 1024:
            return self._responder(413, {"error": "cuerpo vacío o demasiado grande"})
        try:
            msg = json.loads(self.rfile.read(n))
        except ValueError:
            return self._responder(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON no válido"}})
        if isinstance(msg, list):
            res = [r for r in (atender_rpc(m) for m in msg if isinstance(m, dict)) if r]
            return self._responder(200, res) if res else self._responder(202)
        if not isinstance(msg, dict):
            return self._responder(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Petición no válida"}})
        r = atender_rpc(msg)
        self._responder(200, r) if r else self._responder(202)


class Servidor(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ─── Inicio de sesión (flujo de app de escritorio: loopback + PKCE) ───

def scopes_faltantes(concedidos: set[str]) -> list[str]:
    """Scopes pedidos que Google no concedió, contando los alias (EQUIVALENTES) como concedidos."""
    return [s for s in SCOPES if s.startswith("https://")
            and s not in concedidos and not (EQUIVALENTES.get(s, set()) & concedidos)]


def login() -> int:
    c = _cliente()
    verificador = secrets.token_urlsafe(64)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    estado = secrets.token_urlsafe(24)
    resultado: dict = {}

    class Vuelta(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get("state", [""])[0] != estado:
                self.send_response(400); self.end_headers(); self.wfile.write(b"Estado no valido"); return
            resultado.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in resultado
            self.wfile.write(("<h2>JARVIS: " + ("sesión iniciada. Ya puede cerrar esta pestaña." if ok else
                              "Google devolvió un error: " + resultado.get("error", "?")) + "</h2>").encode())

    srv = http.server.HTTPServer(("127.0.0.1", 0), Vuelta)
    redirect = f"http://127.0.0.1:{srv.server_port}/"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent select_account", "state": estado,
        "code_challenge": reto, "code_challenge_method": "S256"})
    print("Abra este enlace e inicie sesión con su cuenta INSTITUCIONAL (se abrirá solo si hay navegador):\n")
    print(url + "\n")
    try:
        import subprocess
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    srv.timeout = 300
    while not resultado:
        srv.handle_request()
    srv.server_close()
    if "error" in resultado:
        print(f"ERROR de Google: {resultado['error']} {resultado.get('error_description', '')}".strip())
        return 1
    r = _post_form(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"], "code": resultado["code"],
                               "code_verifier": verificador, "redirect_uri": redirect, "grant_type": "authorization_code"})
    if not r.get("refresh_token"):
        print("ERROR: Google no entregó refresh_token (revoque el acceso en myaccount.google.com y repita).")
        return 1
    concedidos = set(r.get("scope", "").split())
    faltan = scopes_faltantes(concedidos)
    email = ""
    try:
        req = urllib.request.Request("https://openidconnect.googleapis.com/v1/userinfo",
                                     headers={"Authorization": f"Bearer {r['access_token']}"})
        email = json.loads(urllib.request.urlopen(req, timeout=20).read()).get("email", "")
    except Exception:
        pass
    _guardar({"refresh_token": r["refresh_token"], "scopes": sorted(concedidos), "email": email,
              "creado": datetime.now().astimezone().isoformat(timespec="seconds")})
    print(f"Sesión guardada en {TOKEN} (600) para {email or 'la cuenta elegida'}.")
    if faltan:
        print("AVISO: no se concedieron todos los permisos: " + ", ".join(s.rsplit('/', 1)[-1] for s in faltan))
        return 2
    return 0


def check() -> int:
    """doctor.sh: el token renueva y Classroom responde. Nunca imprime el token."""
    try:
        guardado = json.loads(TOKEN.read_text())
    except FileNotFoundError:
        print("ERROR sin sesión (mcp/escuela/servidor.py login)")
        return 1
    modo = oct(TOKEN.stat().st_mode & 0o777)
    try:
        CRED.token()
        _get(f"{CLASSROOM}/courses", {"studentId": "me", "pageSize": 1})
    except GoogleError as e:
        print(f"ERROR {e}")
        return 1
    print(f"OK {guardado.get('email', '?')} · permisos del archivo {modo}")
    return 0


def main(argv: list[str]) -> int:
    orden = argv[1] if len(argv) > 1 else "serve"
    if orden == "login":
        return login()
    if orden == "check":
        return check()
    if orden == "tareas":
        try:
            for t in tareas():
                print(f"{t['vence'] or 'sin fecha':>17} · {t['curso']} · {t['titulo']}{' (ATRASADA)' if t['atrasada'] else ''}")
        except GoogleError as e:
            print(f"ERROR {e}")
            return 1
        return 0
    if orden == "serve":
        srv = Servidor((HOST, PUERTO), Manejador)
        print(f"[escuela] MCP de solo lectura en http://{HOST}:{PUERTO}/mcp", file=sys.stderr, flush=True)
        srv.serve_forever()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
