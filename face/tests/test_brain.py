"""Puente face → OpenClaw: sesión estable, sin historial, failover con aviso."""
import httpx
import pytest

from jarvis import brain as B


class _Resp:
    def __init__(self, code, data):
        self.status_code, self._d, self.text = code, data, str(data)
    def json(self):
        return self._d


def _ok(texto):
    return _Resp(200, {"choices": [{"message": {"content": texto}}]})


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "t" * 48)


def test_envia_solo_mensaje_nuevo_y_user_estable(monkeypatch):
    vistos = []
    def post(url, json, headers, timeout):
        vistos.append((url, json, headers))
        return _ok("Hola, señor.")
    monkeypatch.setattr(B.httpx, "post", post)
    r, backup = B.Brain().ask("hola")
    assert (r, backup) == ("Hola, señor.", False)
    url, body, headers = vistos[0]
    assert url.endswith("/v1/chat/completions") and url.startswith("http://127.0.0.1:")
    assert body["model"] == "openclaw/jarvis" and body["user"] == "face:jarvis"
    # Solo el mensaje nuevo, precedido de la instrucción de estilo hablado (prosa, sin Markdown) para ambos cerebros.
    sistema = body["messages"][0]
    assert sistema["role"] == "system" and sistema["content"].startswith(B.ESTILO_VOZ + " Ahora: ")
    assert body["messages"][1:] == [{"role": "user", "content": "hola"}]
    assert "prosa" in B.ESTILO_VOZ and "listas" in B.ESTILO_VOZ
    assert headers["Authorization"] == "Bearer " + "t" * 48
    assert "x-openclaw-model" not in headers


def test_limite_de_claude_cambia_a_respaldo_y_avisa(monkeypatch):
    llamadas, avisos = [], []
    def post(url, json, headers, timeout):
        llamadas.append(headers.get("x-openclaw-model"))
        if len(llamadas) == 1:
            return _Resp(500, {"error": {"message": "All models failed (2): anthropic/claude-opus-5-5: usage limit reached"}})
        return _ok("Respuesta de GPT.")
    monkeypatch.setattr(B.httpx, "post", post)
    r, backup = B.Brain(on_backup=avisos.append).ask("hola")
    assert (r, backup) == ("Respuesta de GPT.", True)
    assert llamadas == [None, "openai/gpt-5.6-terra"]
    assert avisos == ["Cambio al cerebro de respaldo."]


def test_timeout_no_reintenta(monkeypatch):
    n = []
    def post(*a, **k):
        n.append(1)
        raise httpx.ReadTimeout("lento")
    monkeypatch.setattr(B.httpx, "post", post)
    with pytest.raises(TimeoutError):
        B.Brain().ask("crea un documento")
    assert len(n) == 1


def test_gateway_caido(monkeypatch):
    def post(*a, **k):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(B.httpx, "post", post)
    with pytest.raises(ConnectionError):
        B.Brain().ask("hola")


def test_error_no_de_modelo_no_cambia(monkeypatch):
    monkeypatch.setattr(B.httpx, "post", lambda *a, **k: _Resp(400, {"error": {"message": "invalid_request_error: bad body"}}))
    with pytest.raises(B.BrainError):
        B.Brain(on_backup=lambda m: pytest.fail("no debía avisar")).ask("hola")


def test_sin_token(monkeypatch):
    monkeypatch.delenv("OPENCLAW_GATEWAY_TOKEN")
    monkeypatch.setattr(B, "_REPO_ENV", B.Path("/nonexistent/.env"))
    monkeypatch.setattr(B, "SECRETS", B.Path("/nonexistent/secrets.env"))
    with pytest.raises(B.BrainError, match="OPENCLAW_GATEWAY_TOKEN"):
        B.Brain().ask("hola")


def test_fecha_actual_da_los_dias_de_la_semana():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    f = B.fecha_actual(datetime(2026, 11, 24, 23, 5, tzinfo=ZoneInfo("America/Lima")))
    assert f.startswith("Ahora: martes 24 de noviembre de 2026, 23:05")
    assert "viernes 27" in f and "jueves 26" in f and "martes 8" in f
