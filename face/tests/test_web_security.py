"""HUD: solo con token (cookie), Host/Origin locales, sin keys en /api/providers."""
import pytest
from fastapi.testclient import TestClient

from jarvis import web

TOK = "x" * 43


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("JARVIS_HUD_TOKEN", TOK)
    monkeypatch.setattr(web, "_port", 7860)
    return TestClient(web.app, base_url="http://127.0.0.1:7860")


def test_sin_token_401(client):
    assert client.get("/api/providers").status_code == 401
    assert client.get("/").status_code == 401


def test_token_malo_401(client):
    assert client.get("/?token=malo", follow_redirects=False).status_code == 401


def test_token_pone_cookie_y_quita_url(client):
    r = client.get(f"/?token={TOK}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    c = r.headers["set-cookie"].lower()
    assert "httponly" in c and "samesite=strict" in c


def test_host_ajeno_421(client):
    assert client.get("/api/providers", headers={"host": "evil.example:7860"}).status_code == 421


def test_providers_sin_keys(client):
    client.cookies.set(web._COOKIE, TOK)
    d = client.get("/api/providers").json()
    texto = str(d).lower()
    assert "api_key" not in texto and "base_url" not in texto
    assert d["providers"]


def test_post_sin_origin_403(client):
    client.cookies.set(web._COOKIE, TOK)
    assert client.post("/api/mute").status_code == 403


def test_put_provider_prohibido(client):
    client.cookies.set(web._COOKIE, TOK)
    r = client.put("/api/providers/x", json={"api_key": "k"}, headers={"origin": "http://127.0.0.1:7860"})
    assert r.status_code == 403


def test_ws_sin_cookie_rechazado(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:7860"}) as ws:
            ws.receive_text()


def test_bind_loopback():
    assert web._HOST == "127.0.0.1"
