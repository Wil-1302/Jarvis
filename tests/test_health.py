from __future__ import annotations

import sys

import httpx
import pytest

from app.config.settings import load_settings
from app.core import health
from app.core.health import CheckResult, Status
from tests.conftest import fake_ollama_handler, offline_handler


def _patch_ollama(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    original = health.OllamaClient

    def factory(host, timeout=30.0):
        return original(host, timeout=timeout, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(health, "OllamaClient", factory)


def test_python_check(settings) -> None:
    result = health.check_python(settings)
    expected = Status.FAIL if sys.version_info[:2] != (3, 12) else Status.OK
    if expected is Status.OK and sys.prefix == sys.base_prefix:
        expected = Status.WARN
    assert result.status is expected


def test_config_check(settings) -> None:
    assert health.check_config(settings).status is Status.OK


def test_workspace_ok_creates_dirs(settings, tmp_path) -> None:
    assert health.check_workspace(settings).status is Status.OK
    assert (tmp_path / "logs").is_dir()


def test_workspace_missing_fails(make_settings, tmp_path) -> None:
    settings = make_settings(workspace=tmp_path / "no-existe")
    assert health.check_workspace(settings).status is Status.FAIL


def test_ollama_and_model_ok(settings, monkeypatch) -> None:
    _patch_ollama(monkeypatch, fake_ollama_handler())
    assert health.check_ollama(settings).status is Status.OK
    assert health.check_model(settings).status is Status.OK


def test_model_missing_fails_with_hint(settings, monkeypatch) -> None:
    _patch_ollama(monkeypatch, fake_ollama_handler(models=["otro:latest"]))
    result = health.check_model(settings)
    assert result.status is Status.FAIL
    assert "ollama pull" in result.detail


def test_ollama_offline_fails(settings, monkeypatch) -> None:
    _patch_ollama(monkeypatch, offline_handler)
    assert health.check_ollama(settings).status is Status.FAIL
    assert health.check_model(settings).status is Status.FAIL


def test_missing_ffmpeg_fails(make_settings) -> None:
    settings = make_settings(ffmpeg_path="ffmpeg-que-no-existe-xyz")
    result = health.check_ffmpeg(settings)
    assert result.status is Status.FAIL
    assert "PATH" in result.detail


def test_missing_claude_is_only_a_warning(make_settings) -> None:
    settings = make_settings(claude_command="claude-que-no-existe-xyz")
    assert health.check_claude(settings).status is Status.WARN


def test_git_fails_outside_repository(settings) -> None:
    assert health.check_git(settings).status is Status.FAIL


def test_github_check_can_be_disabled(settings) -> None:
    assert health.check_github(settings).status is Status.SKIP


def test_missing_voice_models_fail_with_hint(make_settings, tmp_path) -> None:
    settings = make_settings(models_dir=tmp_path / "vacio")
    result = health.check_voice_models(settings)
    assert result.status is Status.FAIL
    assert "--download-models" in result.detail


def test_cuda_check_skipped_on_cpu(make_settings) -> None:
    assert health.check_cuda(make_settings(stt_device="cpu")).status is Status.SKIP


def test_audio_check_reports_missing_device(make_settings) -> None:
    result = health.check_audio(make_settings(audio_input_device="microfono-inexistente-xyz"))
    assert result.status is Status.FAIL


def test_broken_check_does_not_stop_the_rest(settings) -> None:
    def broken(_settings):
        raise RuntimeError("boom")

    def fine(_settings):
        return CheckResult("Fine", Status.OK, "ok")

    results = health.run_health_checks(settings, [broken, fine])
    assert [r.status for r in results] == [Status.FAIL, Status.OK]
    assert not health.is_healthy(results)


def test_is_healthy_ignores_warn_and_skip() -> None:
    results = [
        CheckResult("a", Status.OK, ""),
        CheckResult("b", Status.WARN, ""),
        CheckResult("c", Status.SKIP, ""),
    ]
    assert health.is_healthy(results)


def test_format_results() -> None:
    text = health.format_results(
        [CheckResult("Python", Status.OK, "3.12"), CheckResult("FFmpeg", Status.FAIL, "falta")]
    )
    assert "[OK  ] Python" in text
    assert "[FAIL] FFmpeg" in text


@pytest.mark.integration
def test_real_environment_is_healthy() -> None:
    settings = load_settings(env_file=None)
    results = health.run_health_checks(settings)
    failures = [r for r in results if r.status is Status.FAIL]
    assert not failures, health.format_results(failures)
