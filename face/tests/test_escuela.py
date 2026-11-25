"""MCP «escuela» (D-029): cálculo de pendientes, JSON-RPC y cliente MCP contra el servidor real (sin Google)."""
import importlib.util
import json
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from jarvis.mcp_cliente import Cliente, MCPError, _leer_sse

RUTA = Path(__file__).resolve().parents[2] / "mcp" / "escuela" / "servidor.py"
spec = importlib.util.spec_from_file_location("servidor_escuela", RUTA)
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
LIMA = ZoneInfo("America/Lima")


def cw(i, d=None, t=None, titulo="T"):
    x = {"id": i, "title": titulo, "workType": "ASSIGNMENT"}
    if d:
        x["dueDate"] = dict(zip(("year", "month", "day"), d))
    if t:
        x["dueTime"] = dict(zip(("hours", "minutes"), t))
    return x


def test_pendientes():
    ahora = datetime(2026, 11, 24, 12, 0, tzinfo=LIMA)
    trabajos = {"A": [cw("1", (2026, 11, 26), (5, 0), "Informe"), cw("2", (2026, 11, 25), None, "Ensayo"),
                      cw("3", (2026, 11, 27), (12, 0), "Entregada"), cw("4", None, None, "Sin fecha"),
                      cw("5", (2026, 10, 1), (12, 0), "Vieja"), cw("6", (2026, 11, 30), None, "No asignada")]}
    entregas = {"A": [{"courseWorkId": "1", "state": "CREATED"}, {"courseWorkId": "2", "state": "NEW"},
                      {"courseWorkId": "3", "state": "TURNED_IN"}, {"courseWorkId": "4", "state": "CREATED"},
                      {"courseWorkId": "5", "state": "CREATED"}]}
    r = srv.tareas_pendientes(trabajos.get, entregas.get, [{"id": "A", "nombre": "Redes"}], ahora=ahora)
    assert [t["titulo"] for t in r] == ["Ensayo", "Informe", "Sin fecha"]
    assert r[1]["vence"].startswith("2026-11-26T00:00")   # 05:00 UTC = 00:00 en Lima
    assert r[0]["vence"].startswith("2026-11-25T23:59")   # sin hora → fin del día
    assert r[2]["vence"] is None
    sin = srv.tareas_pendientes(trabajos.get, entregas.get, [{"id": "A", "nombre": "Redes"}], ahora=ahora,
                                incluir_sin_fecha=False)
    assert len(sin) == 2


def test_rpc_basico():
    r = srv.atender_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert srv.atender_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    nombres = {t["name"] for t in srv.atender_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
    assert nombres == {"tareas_pendientes", "cursos", "eventos_institucionales"}
    assert all(t["annotations"]["readOnlyHint"] for t in srv.HERRAMIENTAS)
    assert "error" in srv.atender_rpc({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})


def test_solo_scopes_de_lectura():
    for s in srv.SCOPES:
        assert s in ("openid", "email") or s.endswith(".readonly"), s


@pytest.fixture
def servidor(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "TOKEN", tmp_path / "no-hay.json")
    monkeypatch.setattr(srv, "CLIENTE", tmp_path / "no-hay-cliente.json")
    s = srv.Servidor(("127.0.0.1", 0), srv.Manejador)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}/mcp"
    s.shutdown()


def test_cliente_contra_servidor(servidor):
    c = Cliente(servidor, timeout=5)
    with pytest.raises(MCPError, match="Error de Google: Sin sesión de la cuenta institucional"):
        c.herramienta("tareas_pendientes")
    with pytest.raises(MCPError, match="desconocida"):
        c.herramienta("borrar_todo")


def test_host_y_origin_ajenos(servidor):
    import urllib.request, urllib.error
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
    for cab in ({"Host": "evil.example"}, {"Origin": "http://evil.example"}):
        req = urllib.request.Request(servidor, data=body, headers={"Content-Type": "application/json", **cab})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 403


def test_cliente_solo_local():
    with pytest.raises(ValueError):
        Cliente("http://example.com/mcp")


def test_sse():
    cuerpo = 'event: message\ndata: {"jsonrpc":"2.0","method":"x"}\n\nevent: message\ndata: {"jsonrpc":"2.0","id":7,"result":{"ok":1}}\n\n'
    assert _leer_sse(cuerpo, 7)["result"] == {"ok": 1}


def test_alias_de_coursework_no_cuenta_como_faltante():
    """Google concede student-submissions.me.readonly en lugar de coursework.me.readonly: no es un permiso faltante."""
    base = "https://www.googleapis.com/auth/"
    concedidos = {base + "classroom.courses.readonly", base + "classroom.student-submissions.me.readonly",
                  base + "calendar.readonly", "openid"}
    assert srv.scopes_faltantes(concedidos) == []
    assert srv.scopes_faltantes(concedidos - {base + "calendar.readonly"}) == [base + "calendar.readonly"]
    sin_classroom = concedidos - {base + "classroom.student-submissions.me.readonly"}
    assert len(srv.scopes_faltantes(sin_classroom)) == 2


def test_fecha_dicha_con_dia_de_la_semana():
    assert srv.fecha_dicha(datetime(2026, 11, 27, 23, 59, tzinfo=LIMA)) == "viernes 27 de noviembre, 23:59"
    assert srv.fecha_dicha(datetime(2026, 11, 24, 8, 5, tzinfo=LIMA)) == "martes 24 de noviembre, 08:05"
