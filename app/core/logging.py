"""Logging de JARVIS: fichero rotativo en ``logs/jarvis.log`` con redacción de secretos."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from app.config.settings import Settings

LOGGER_NAME = "jarvis"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Patrones que nunca deben acabar en un log.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),  # Anthropic / OpenAI
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),  # GitHub
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:api[_-]?key|token|secret|password|passwd)[A-Z0-9_]*)"
        r"(\s*[=:]\s*)(['\"]?)[^\s'\",]+"
    ),
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 3:
            text = pattern.sub(r"\1\2\3***", text)
        else:
            text = pattern.sub("***", text)
    return text


class RedactingFilter(logging.Filter):
    """Reemplaza secretos en el mensaje final antes de escribirlo."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def setup_logging(settings: Settings, *, console: bool = False) -> logging.Logger:
    """Configura el logger ``jarvis``. Es idempotente: reemplaza handlers previos."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(settings.log_level)
    logger.propagate = False

    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        settings.log_path,
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    handlers: list[logging.Handler] = [file_handler]
    if console:
        handlers.append(logging.StreamHandler())

    for handler in handlers:
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
