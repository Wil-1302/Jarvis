from __future__ import annotations

import logging

import pytest

from app.core.logging import LOGGER_NAME, get_logger, redact, setup_logging


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        ("ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnop", "sk-ant-api03"),
        ("token: ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdef"),
        ("Authorization: Bearer abc.def.ghijklmnop", "abc.def"),
        ("password='hunter22'", "hunter22"),
        ("client_secret = s3cr3tvalue", "s3cr3tvalue"),
    ],
)
def test_redact_removes_secrets(raw: str, leaked: str) -> None:
    cleaned = redact(raw)
    assert leaked not in cleaned
    assert "***" in cleaned


def test_redact_keeps_normal_text() -> None:
    text = "Modelo qwen3:4b-instruct disponible en http://127.0.0.1:11434"
    assert redact(text) == text


def test_setup_logging_writes_file(settings) -> None:
    logger = setup_logging(settings)
    get_logger("test").info("inicio de prueba")
    for handler in logger.handlers:
        handler.flush()
    content = settings.log_path.read_text(encoding="utf-8")
    assert "inicio de prueba" in content
    assert "jarvis.test" in content


def test_log_file_never_contains_secrets(settings) -> None:
    setup_logging(settings)
    get_logger("test").info("config: %s", {"api_key": "sk-ant-secret1234567890"})
    get_logger("test").error("fallo con GH_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123")
    content = settings.log_path.read_text(encoding="utf-8")
    assert "sk-ant-secret" not in content
    assert "ghp_abcdef" not in content


def test_setup_logging_is_idempotent(settings) -> None:
    setup_logging(settings)
    logger = setup_logging(settings)
    assert len(logger.handlers) == 1
    assert logging.getLogger(LOGGER_NAME) is logger


def test_log_level_from_settings(make_settings) -> None:
    logger = setup_logging(make_settings(log_level="DEBUG"))
    assert logger.level == logging.DEBUG
