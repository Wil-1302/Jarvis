from __future__ import annotations

import subprocess
import sys

import pytest

from app import __version__, cli
from app.config.settings import PROJECT_ROOT
from app.core.health import CheckResult, Status
from app.core.jarvis import JarvisCore


def _inputs(*lines: str):
    it = iter(lines)

    def fake_input(_prompt: str) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    return fake_input


def test_core_replies(settings, fake_ollama) -> None:
    core = JarvisCore(settings, ollama=fake_ollama)
    core.start()
    assert "funcionando" in core.handle("hello").text
    assert "funcionando" in core.handle("﻿Hola!").text  # BOM de PowerShell
    assert "qwen3:4b-instruct disponible" in core.handle("estado").text
    assert core.handle("salir").exit
    assert core.handle("   ").text == ""
    core.shutdown()
    assert not core.running


def test_core_start_without_ollama(settings, offline_ollama) -> None:
    core = JarvisCore(settings, ollama=offline_ollama)
    status = core.start()
    assert not status.ollama_connected
    assert "desconectado" in core.handle("estado").text


def test_repl_banner_and_hello(settings, fake_ollama, capsys) -> None:
    core = JarvisCore(settings, ollama=fake_ollama)
    code = cli.run_repl(settings, core=core, input_fn=_inputs("hello", "salir"))
    out = capsys.readouterr().out
    assert code == 0
    assert "JARVIS-WIL" in out
    assert "Environment: development" in out
    assert "Ollama: connected" in out
    assert "Model: qwen3:4b-instruct" in out
    assert "JARVIS core initialized successfully." in out
    assert "el core está funcionando" in out
    assert not core.running


def test_repl_ends_on_eof(settings, fake_ollama) -> None:
    core = JarvisCore(settings, ollama=fake_ollama)
    assert cli.run_repl(settings, core=core, input_fn=_inputs()) == 0


def test_main_health_exit_codes(settings, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: settings)

    monkeypatch.setattr(
        cli, "run_health_checks", lambda s: [CheckResult("Python", Status.OK, "3.12")]
    )
    assert cli.main(["--health"]) == 0
    assert "[OK  ] Python" in capsys.readouterr().out

    monkeypatch.setattr(
        cli, "run_health_checks", lambda s: [CheckResult("FFmpeg", Status.FAIL, "falta")]
    )
    assert cli.main(["--health"]) == 1
    assert "[FAIL] FFmpeg" in capsys.readouterr().out


def test_main_logs_start_and_end(settings, monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "run_health_checks", lambda s: [])
    cli.main(["--health"])
    log = settings.log_path.read_text(encoding="utf-8")
    assert "CLI iniciada" in log
    assert "CLI finalizada" in log


def test_main_reports_config_errors(monkeypatch, capsys) -> None:
    monkeypatch.setenv("JARVIS_ENV", "staging")
    assert cli.main(["--health"]) == 2
    assert "[FAIL]" in capsys.readouterr().err


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_python_dash_m_app_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app", "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert f"JARVIS-WIL {__version__}" in result.stdout
