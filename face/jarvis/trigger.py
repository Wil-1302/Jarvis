"""Disparador local: socket Unix en $XDG_RUNTIME_DIR/jarvis/face.sock (carpeta 700, sin red).

El atajo global (Super+J en Hyprland) ejecuta `jarvis-escucha`, que escribe "listen" aquí:
abre la conversación sin decir el nombre (si está hablando o pensando, lo detiene). "stop" lo detiene todo.
"""
from __future__ import annotations

import os
import socket
import threading
from pathlib import Path

SOCK = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "jarvis" / "face.sock"


def _serve() -> None:
    SOCK.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(SOCK.parent, 0o700)
    try:
        SOCK.unlink()
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCK))
    os.chmod(SOCK, 0o600)
    srv.listen(4)
    print(f"[Atajo] Esperando órdenes en {SOCK}")
    from jarvis.main import trigger
    while True:
        conn, _ = srv.accept()
        with conn:
            conn.settimeout(1.0)
            try:
                cmd = conn.recv(64).decode(errors="ignore").strip()
            except OSError:
                continue
            if cmd == "listen":
                print("[Atajo] Activación por teclado.")
                trigger("atajo")
                conn.sendall(b"ok\n")
            elif cmd == "stop":
                from jarvis.main import abort_all
                abort_all()
                conn.sendall(b"ok\n")
            else:
                conn.sendall(b"?\n")


def start_trigger_server() -> None:
    threading.Thread(target=_serve, name="trigger", daemon=True).start()
