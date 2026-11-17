"""Jarvis Web UI — runs alongside voice as a background thread."""
from __future__ import annotations
import asyncio
import json
import threading
from pathlib import Path

import hmac
import os
import secrets

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from jarvis.tts import speak_streamed, stop_speaking, is_speaking

_STATIC_DIR = Path(__file__).parent / "static"
_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"
_HOST = "127.0.0.1"          # el HUD NUNCA escucha fuera de loopback (CLAUDE.md)
_COOKIE = "jarvis_hud"
_port = 7860

app = FastAPI(title="Jarvis", docs_url=None, redoc_url=None, openapi_url=None)


# ─── Seguridad del HUD: token (cookie HttpOnly) + Host/Origin locales ───

def _hud_token() -> str:
    """JARVIS_HUD_TOKEN del entorno o del .env; si no existe, se genera y se guarda (600)."""
    tok = os.environ.get("JARVIS_HUD_TOKEN", "")
    if tok:
        return tok
    lines = []
    if _REPO_ENV.exists():
        lines = _REPO_ENV.read_text(encoding="utf-8").splitlines()
        for ln in lines:
            if ln.startswith("JARVIS_HUD_TOKEN=") and len(ln) > 20:
                tok = ln.split("=", 1)[1].strip()
    if not tok:
        tok = secrets.token_urlsafe(32)
        fd = os.open(_REPO_ENV, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            f.write(f"JARVIS_HUD_TOKEN={tok}\n")
        os.chmod(_REPO_ENV, 0o600)
    os.environ["JARVIS_HUD_TOKEN"] = tok
    return tok


def hud_url(port: int = 7860, con_token: bool = True) -> str:
    base = f"http://{_HOST}:{port}/"
    return f"{base}?token={_hud_token()}" if con_token else base


def _ok_token(valor: str | None) -> bool:
    return bool(valor) and hmac.compare_digest(valor, _hud_token())


def _hosts_validos() -> set[str]:
    return {f"127.0.0.1:{_port}", f"localhost:{_port}"}


def _origen_valido(origin: str | None) -> bool:
    return origin in {f"http://{h}" for h in _hosts_validos()}


@app.middleware("http")
async def _seguridad(request: Request, call_next):
    if request.headers.get("host") not in _hosts_validos():     # anti DNS rebinding
        return JSONResponse({"error": "host no permitido"}, status_code=421)
    if request.url.path == "/" and _ok_token(request.query_params.get("token")):
        resp = RedirectResponse("/", status_code=303)            # quita el token de la URL
        resp.set_cookie(_COOKIE, _hud_token(), httponly=True, samesite="strict", path="/")
        return resp
    if not _ok_token(request.cookies.get(_COOKIE)):
        return JSONResponse({"error": "no autorizado: abre el enlace con token que muestra JARVIS"},
                            status_code=401)
    if request.method not in ("GET", "HEAD") and not _origen_valido(request.headers.get("origin")):
        return JSONResponse({"error": "origen no permitido"}, status_code=403)   # anti CSRF
    return await call_next(request)
_clients: list[WebSocket] = []
_loop: asyncio.AbstractEventLoop | None = None


# ─── Capture the REAL event loop at startup ───

@app.on_event("startup")
async def _capture_loop():
    global _loop
    _loop = asyncio.get_running_loop()
    print("[Web] Event loop captured — WebSocket broadcast ready.")


# ─── Thread-safe broadcast ───

def _broadcast_to_ws(event: dict) -> None:
    """Send event to all connected WebSocket clients.
    Thread-safe — can be called from voice/keyboard threads."""
    if not _loop or _loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(_async_broadcast(event), _loop)
    except RuntimeError:
        pass  # loop closed during shutdown


async def _async_broadcast(event: dict) -> None:
    """Actually send the event — runs on the event loop thread."""
    data = json.dumps(event)
    for ws in list(_clients):
        try:
            await ws.send_text(data)
        except Exception:
            if ws in _clients:
                _clients.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))


# ─── Provider APIs ───

@app.get("/api/providers")
async def api_providers():
    """Cerebros disponibles (OpenClaw). Nunca devuelve keys ni URLs."""
    from jarvis.main import get_providers, get_active_provider
    result = {k: {"label": v.get("label", k), "model": v.get("model") or "", "type": "openclaw"}
              for k, v in get_providers().items()}
    return JSONResponse({"providers": result, "active": get_active_provider()})


@app.post("/api/providers/{provider_key}")
async def api_set_provider(provider_key: str):
    from jarvis.main import set_active_provider
    if set_active_provider(provider_key):
        return JSONResponse({"status": "ok", "active": provider_key})
    return JSONResponse({"status": "error", "message": "Cerebro desconocido"}, status_code=400)


@app.put("/api/providers/{provider_key}")
@app.delete("/api/providers/{provider_key}")
async def api_providers_readonly(provider_key: str):
    """Los modelos y credenciales se gestionan en OpenClaw, no desde el HUD."""
    return JSONResponse({"status": "error", "message": "Se gestiona en OpenClaw (brain/config)."},
                        status_code=403)


# ─── Settings APIs ───

@app.get("/api/settings")
async def api_get_settings():
    """Return all configurable settings."""
    from jarvis.main import _load_config
    cfg = _load_config()
    return JSONResponse({
        "tts": cfg.get("tts", {}),
        "stt": cfg.get("stt", {}),
        "wake_word": cfg.get("wake_word", {}),
        "llm": {"active_provider": cfg.get("llm", {}).get("active_brain", "auto")},
    })


@app.put("/api/settings")
async def api_update_settings(request: Request):
    """Update settings. Accepts partial updates."""
    from jarvis.main import _load_config, _save_config
    body = await request.json()
    cfg = _load_config()

    if "tts" in body:
        cfg.setdefault("tts", {}).update(body["tts"])
    if "stt" in body:
        cfg.setdefault("stt", {}).update(body["stt"])
    if "wake_word" in body:
        cfg.setdefault("wake_word", {}).update(body["wake_word"])

    _save_config(cfg)
    return JSONResponse({"status": "ok"})


# ─── Mute APIs ───

@app.get("/api/mute")
async def api_get_mute():
    from jarvis.main import is_muted
    return JSONResponse({"muted": is_muted()})


@app.post("/api/mute")
async def api_toggle_mute():
    from jarvis.main import toggle_mute, is_muted
    toggle_mute()
    return JSONResponse({"muted": is_muted()})


# ─── WebSocket ───

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # El middleware HTTP no cubre WebSocket: mismas comprobaciones aquí (anti CSWSH).
    if (ws.headers.get("host") not in _hosts_validos() or not _origen_valido(ws.headers.get("origin"))
            or not _ok_token(ws.cookies.get(_COOKIE))):
        await ws.close(code=4401)
        return
    await ws.accept()
    _clients.append(ws)
    await ws.send_text(json.dumps({"type": "connected", "message": "JARVIS en línea."}))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "chat":
                user_text = msg["text"]

                # "stop" typed in chat = abort everything
                from jarvis.main import _is_stop_command
                if _is_stop_command(user_text):
                    from jarvis.main import abort_all
                    abort_all()
                    await ws.send_text(json.dumps({"type": "response", "text": "Detenido."}))
                    continue

                from jarvis.main import _process_request, _Aborted
                loop = asyncio.get_event_loop()
                try:
                    response = await loop.run_in_executor(
                        None, _process_request, user_text,
                    )
                    from jarvis.main import _speak_streamed_if_unmuted
                    threading.Thread(target=_speak_streamed_if_unmuted, args=(response,), daemon=True).start()
                except _Aborted:
                    await ws.send_text(json.dumps({"type": "response", "text": "Detenido."}))
                except Exception as e:
                    await ws.send_text(json.dumps({"type": "response", "text": "Error al procesar la orden."}))

            elif msg.get("type") == "interrupt":
                from jarvis.main import abort_all
                abort_all()

    except WebSocketDisconnect:
        if ws in _clients:
            _clients.remove(ws)


def start_web_background(port: int = 7860) -> None:
    """Lanza el HUD en un hilo (solo 127.0.0.1, con token)."""
    global _port
    _port = port
    _hud_token()
    from jarvis.main import register_event_listener
    register_event_listener(_broadcast_to_ws)

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(app, host=_HOST, port=port, log_level="warning")
        server = uvicorn.Server(config)
        loop.run_until_complete(server.serve())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
