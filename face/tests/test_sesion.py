"""Arranque antes de la sesión gráfica (linger): face sin WAYLAND_DISPLAY ni HYPRLAND_INSTANCE_SIGNATURE.
Tras dos reinicios Spotify falló con «No consigo ponerla»: hyprctl no veía a Hyprland y no lo abría."""
import os
import subprocess

import pytest

import jarvis.acciones as A
import jarvis.sesion as SE
import jarvis.spotify as S

SIG = "abc123_1795101107_2111524030"


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Un $XDG_RUNTIME_DIR con Hyprland ya en marcha, y un face que arrancó sin sus variables."""
    (tmp_path / "hypr" / SIG).mkdir(parents=True)
    (tmp_path / "hypr" / SIG / ".socket.sock").touch()
    (tmp_path / "wayland-1").touch()
    (tmp_path / "wayland-1.lock").touch()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    return tmp_path


def _gestor(monkeypatch, salida=""):
    monkeypatch.setattr(SE.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, salida, ""))


def test_recupera_el_entorno_del_gestor_de_systemd(runtime, monkeypatch):
    _gestor(monkeypatch, f"HYPRLAND_INSTANCE_SIGNATURE={SIG}\nWAYLAND_DISPLAY=wayland-1\nOTRA=x\n")
    assert SE.asegurar_entorno()
    assert os.environ["HYPRLAND_INSTANCE_SIGNATURE"] == SIG and os.environ["WAYLAND_DISPLAY"] == "wayland-1"
    assert "OTRA" not in os.environ


def test_sin_gestor_lo_saca_de_los_sockets(runtime, monkeypatch):
    _gestor(monkeypatch, "")   # el gestor tampoco las tiene (sesión sin uwsm)
    assert SE.asegurar_entorno()
    assert os.environ["HYPRLAND_INSTANCE_SIGNATURE"] == SIG and os.environ["WAYLAND_DISPLAY"] == "wayland-1"


def test_firma_caducada_de_un_hyprland_anterior_se_corrige(runtime, monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "vieja_123")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    _gestor(monkeypatch, "")
    assert SE.asegurar_entorno() and os.environ["HYPRLAND_INSTANCE_SIGNATURE"] == SIG


def test_sin_hyprland_no_inventa_nada(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    _gestor(monkeypatch, "")
    assert not SE.asegurar_entorno() and "HYPRLAND_INSTANCE_SIGNATURE" not in os.environ


# ─── Lo que dice Jarvis: la causa real, no «No consigo ponerla» ───
@pytest.fixture
def sp(monkeypatch):
    monkeypatch.setattr(S, "_api_inutil", True)
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(S, "ventana_abierta", lambda: False)


def test_spotify_cerrado_y_sin_sesion_lo_dice(sp, monkeypatch):
    monkeypatch.setattr(S.sesion, "asegurar_entorno", lambda: False)
    monkeypatch.setattr(S, "abierto", lambda: False)
    r, _ = A.intentar("pon todavía me amas de aventura en spotify")
    assert "no está abierto" in r and "sesión gráfica" in r


def test_spotify_que_no_arranca_lo_dice(sp, monkeypatch):
    monkeypatch.setattr(S.sesion, "asegurar_entorno", lambda: True)
    monkeypatch.setattr(S, "abierto", lambda: False)
    monkeypatch.setattr(S.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "ok", ""))
    r, _ = A.intentar("pon música de cerati")
    assert "Spotify no está abierto y no terminó de arrancar" in r


def test_sin_permiso_de_uinput_dice_que_no_tiene_teclado(sp, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))   # sin .ydotool_socket
    monkeypatch.setattr(S.sesion, "asegurar_entorno", lambda: True)
    monkeypatch.setattr(S, "abierto", lambda: True)
    monkeypatch.setattr(S, "ventana_abierta", lambda: True)
    monkeypatch.setattr(S.sesion, "uinput_accesible", lambda: False)
    monkeypatch.setattr(S.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3, "", ""))
    r, _ = A.intentar("pon crimen de gustavo cerati")
    assert "No tengo control del teclado" in r


def test_pausa_con_spotify_cerrado(sp, monkeypatch):
    monkeypatch.setattr(S, "abierto", lambda: False)
    r, _ = A.intentar("pausa")
    assert r == "Spotify no está abierto."
