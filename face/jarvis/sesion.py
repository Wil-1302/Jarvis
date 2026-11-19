"""Entorno de la sesión gráfica (Hyprland/Wayland) para las acciones de escritorio.

face es un servicio de usuario. Si arrancó antes que la sesión gráfica (linger), no tiene WAYLAND_DISPLAY ni
HYPRLAND_INSTANCE_SIGNATURE y `hyprctl`, `wl-copy` y `ydotool` fallan aunque Hyprland ya esté en pantalla. La
unidad arranca con graphical-session.target; esto es la red de seguridad: antes de actuar se recupera el entorno
del gestor de systemd (uwsm lo importa ahí) o, si no, de los sockets de $XDG_RUNTIME_DIR.
"""
from __future__ import annotations

import glob
import os
import subprocess

VARS = ("WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE")


def _runtime() -> str:
    return os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"


def _hypr_valida(sig: str | None) -> bool:
    return bool(sig) and os.path.exists(os.path.join(_runtime(), "hypr", sig, ".socket.sock"))


def _wayland_valido(d: str | None) -> bool:
    return bool(d) and os.path.exists(d if os.path.isabs(d) else os.path.join(_runtime(), d))


def _del_gestor() -> dict[str, str]:
    """Entorno de activación del gestor de systemd de usuario (donde uwsm deja las variables de la sesión)."""
    try:
        r = subprocess.run(["systemctl", "--user", "show-environment"], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return {}
    return dict(l.split("=", 1) for l in r.stdout.splitlines() if l.split("=", 1)[0] in VARS)


def _de_sockets() -> dict[str, str]:
    """Última instancia de Hyprland viva y su socket de Wayland, mirando $XDG_RUNTIME_DIR."""
    rt, env = _runtime(), {}
    socks = sorted(glob.glob(os.path.join(rt, "hypr", "*", ".socket.sock")), key=os.path.getmtime, reverse=True)
    if socks:
        env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(os.path.dirname(socks[0]))
    way = sorted((p for p in glob.glob(os.path.join(rt, "wayland-*")) if not p.endswith(".lock")),
                 key=os.path.getmtime, reverse=True)
    if way:
        env["WAYLAND_DISPLAY"] = os.path.basename(way[0])
    return env


def asegurar_entorno() -> bool:
    """Completa o corrige WAYLAND_DISPLAY e HYPRLAND_INSTANCE_SIGNATURE en os.environ (los hijos lo heredan).
    True si al final hay una sesión de Hyprland utilizable."""
    os.environ.setdefault("XDG_RUNTIME_DIR", _runtime())
    if _hypr_valida(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and _wayland_valido(os.environ.get("WAYLAND_DISPLAY")):
        return True
    for fuente in (_del_gestor, _de_sockets):
        env = fuente()
        cambiado = []
        if not _hypr_valida(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and _hypr_valida(env.get("HYPRLAND_INSTANCE_SIGNATURE")):
            os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = env["HYPRLAND_INSTANCE_SIGNATURE"]
            cambiado.append("HYPRLAND_INSTANCE_SIGNATURE")
        if not _wayland_valido(os.environ.get("WAYLAND_DISPLAY")) and _wayland_valido(env.get("WAYLAND_DISPLAY")):
            os.environ["WAYLAND_DISPLAY"] = env["WAYLAND_DISPLAY"]
            cambiado.append("WAYLAND_DISPLAY")
        if cambiado:
            print(f"[Sesión] entorno gráfico recuperado ({fuente.__name__.strip('_')}): {', '.join(cambiado)}")
        if _hypr_valida(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")) and _wayland_valido(os.environ.get("WAYLAND_DISPLAY")):
            return True
    return False


def uinput_accesible() -> bool:
    """¿Puede el usuario escribir en /dev/uinput? (logind lo concede por ACL al iniciar sesión en el asiento)."""
    return os.access("/dev/uinput", os.W_OK)
