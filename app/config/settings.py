"""Configuración central de JARVIS-WIL.

Orden de prioridad (de mayor a menor):

1. Variables de entorno del proceso.
2. Fichero ``.env`` en la raíz del proyecto (no versionado).
3. ``config/jarvis.toml`` (valores por defecto versionados, sin secretos).
4. Valores por defecto definidos en :class:`Settings`.

La mayoría de variables usan el prefijo ``JARVIS_`` (p. ej. ``JARVIS_LANGUAGE``).
Las que comparten nombre con herramientas externas (``OLLAMA_HOST``,
``OLLAMA_MODEL``, ``CLAUDE_COMMAND``) se leen sin prefijo.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "config" / "jarvis.toml"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

# Fragmentos de nombre que identifican un campo sensible: nunca se muestran ni se registran.
SECRET_HINTS = ("key", "token", "secret", "password")


class ConfigError(Exception):
    """La configuración no se pudo cargar o no es válida."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_by_name=True,
        validate_by_alias=True,
    )

    # --- Identidad ---------------------------------------------------------
    name: str = "Jarvis"
    language: str = "es"
    wake_word: str = "jarvis"
    env: Literal["development", "production", "test"] = "development"

    # --- Workspace ---------------------------------------------------------
    workspace: Path = PROJECT_ROOT

    # --- Cerebro / LLM -----------------------------------------------------
    llm_provider: Literal["hybrid", "ollama", "claude"] = "hybrid"
    ollama_host: str = Field("http://127.0.0.1:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field("qwen3:4b-instruct", alias="OLLAMA_MODEL")
    ollama_timeout: float = 30.0
    claude_command: str = Field("claude", alias="CLAUDE_COMMAND")

    # --- Logging -----------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_file: Path = Path("logs/jarvis.log")
    log_max_bytes: int = 1_000_000
    log_backup_count: int = 5

    # --- Permisos (se aplicarán a las herramientas a partir de la Fase 3) --
    allow_shell: bool = False
    allow_file_write: bool = False
    require_confirmation: bool = True
    allowed_paths: list[Path] = Field(default_factory=list)

    # --- Health check / externos -------------------------------------------
    github_remote: str = "git@github.com:Wil-1302/Jarvis.git"
    check_github: bool = True
    ffmpeg_path: str = "ffmpeg"

    @field_validator("ollama_host")
    @classmethod
    def _normalize_host(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            value = f"http://{value}"
        return value

    @field_validator("workspace")
    @classmethod
    def _absolute_workspace(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("language", "wake_word")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Los valores del TOML llegan como init kwargs y deben tener la prioridad más baja.
        return env_settings, dotenv_settings, init_settings, file_secret_settings

    # --- Rutas derivadas -----------------------------------------------------
    def resolve(self, path: Path) -> Path:
        """Convierte rutas relativas en rutas dentro del workspace."""
        return path if path.is_absolute() else self.workspace / path

    @property
    def log_path(self) -> Path:
        return self.resolve(self.log_file)

    @property
    def data_dirs(self) -> dict[str, Path]:
        return {
            name: self.workspace / name
            for name in ("logs", "memory", "projects", "research", "downloads")
        }

    def ensure_dirs(self) -> None:
        for path in self.data_dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def safe_dump(self) -> dict[str, Any]:
        """Configuración apta para mostrar o registrar: los campos sensibles se enmascaran."""
        data = self.model_dump(mode="json")
        return {
            key: "***" if any(hint in key.lower() for hint in SECRET_HINTS) and value else value
            for key, value in data.items()
        }


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: TOML inválido: {exc}") from exc

    unknown = sorted(set(data) - set(Settings.model_fields))
    if unknown:
        raise ConfigError(f"{path}: claves desconocidas: {', '.join(unknown)}")
    return data


def load_settings(
    config_file: Path | None = DEFAULT_CONFIG_FILE,
    env_file: Path | None = DEFAULT_ENV_FILE,
) -> Settings:
    """Carga la configuración combinando TOML, ``.env`` y entorno.

    Pasar ``None`` desactiva esa fuente (útil en tests).
    """
    toml_values = _read_toml(config_file) if config_file else {}
    try:
        return Settings(_env_file=env_file, **toml_values)
    except ValidationError as exc:
        raise ConfigError(f"Configuración inválida:\n{exc}") from exc
