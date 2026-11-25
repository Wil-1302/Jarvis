"""Cliente MCP mínimo (Streamable HTTP) para los servidores locales de Google (D-029). Solo biblioteca estándar.

face lo usa para los avisos proactivos y la alarma del PC sin pasar por el cerebro (sin gastar modelo cada 15 min);
doctor.sh, para comprobar que los tokens siguen valiendo. Solo habla con 127.0.0.1.
"""
from __future__ import annotations

import itertools
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

CALENDARIO = "http://127.0.0.1:18820/mcp"
ESCUELA = "http://127.0.0.1:18821/mcp"
_PROTOCOLO = "2025-06-18"


class MCPError(Exception):
    pass


def _leer_sse(cuerpo: str, mid: int) -> dict:
    """Respuesta en text/event-stream: el primer `data:` con nuestro id."""
    datos: list[str] = []
    for linea in cuerpo.splitlines() + [""]:
        if linea.startswith("data:"):
            datos.append(linea[5:].lstrip())
        elif not linea and datos:
            try:
                m = json.loads("\n".join(datos))
            except ValueError:
                m = None
            datos = []
            if isinstance(m, dict) and m.get("id") == mid:
                return m
    raise MCPError("respuesta SSE sin resultado")


class Cliente:
    def __init__(self, url: str, timeout: float = 30) -> None:
        host = urllib.parse.urlsplit(url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("solo servidores MCP locales")
        self.url, self.timeout = url, timeout
        self.sesion: str | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._iniciado = False

    def _post(self, msg: dict) -> dict | None:
        cab = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": _PROTOCOLO}
        if self.sesion:
            cab["Mcp-Session-Id"] = self.sesion
        req = urllib.request.Request(self.url, data=json.dumps(msg).encode(), headers=cab, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.sesion = r.headers.get("Mcp-Session-Id") or self.sesion
                cuerpo = r.read().decode("utf-8", "replace")
                tipo = r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code == 404 and self.sesion:   # sesión caducada (reinicio del servidor)
                self.sesion, self._iniciado = None, False
            raise MCPError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}") from None
        except (urllib.error.URLError, OSError) as e:
            raise MCPError(f"servidor no disponible ({self.url}): {getattr(e, 'reason', e)}") from None
        if "id" not in msg or not cuerpo.strip():
            return None
        m = _leer_sse(cuerpo, msg["id"]) if "text/event-stream" in tipo else json.loads(cuerpo)
        if "error" in m:
            raise MCPError(m["error"].get("message", str(m["error"])))
        return m.get("result")

    def _iniciar(self) -> None:
        self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": "initialize",
                    "params": {"protocolVersion": _PROTOCOLO, "capabilities": {},
                               "clientInfo": {"name": "jarvis-face", "version": "1"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._iniciado = True

    def herramienta(self, nombre: str, argumentos: dict | None = None):
        """Llama a una herramienta. Devuelve structuredContent o, si no hay, el JSON/texto del primer bloque."""
        with self._lock:
            for intento in (0, 1):
                if not self._iniciado:
                    self._iniciar()
                try:
                    r = self._post({"jsonrpc": "2.0", "id": next(self._ids), "method": "tools/call",
                                    "params": {"name": nombre, "arguments": argumentos or {}}})
                    break
                except MCPError:
                    if intento or self._iniciado:   # solo se reintenta si la sesión caducó (404)
                        raise
        texto = "".join(c.get("text", "") for c in (r or {}).get("content", []) if c.get("type") == "text")
        if (r or {}).get("isError"):
            raise MCPError(texto or "error de la herramienta")
        if r and r.get("structuredContent") is not None:
            return r["structuredContent"]
        try:
            return json.loads(texto)
        except ValueError:
            return texto


if __name__ == "__main__":   # prueba: python -m jarvis.mcp_cliente <url> <herramienta> ['{json}']
    import sys
    c = Cliente(sys.argv[1])
    print(json.dumps(c.herramienta(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}),
                     ensure_ascii=False, indent=1))
