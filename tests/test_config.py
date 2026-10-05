from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.config.settings import (
    DEFAULT_CONFIG_FILE,
    PROJECT_ROOT,
    ConfigError,
    Settings,
    load_settings,
)


def test_defaults_without_files() -> None:
    settings = load_settings(config_file=None, env_file=None)
    assert settings.name == "Jarvis"
    assert settings.language == "es"
    assert settings.wake_word == "jarvis"
    assert settings.env == "development"
    assert settings.llm_provider == "hybrid"
    assert settings.ollama_model == "qwen3:4b-instruct"
    assert settings.workspace == PROJECT_ROOT
    assert settings.allow_shell is False
    assert settings.require_confirmation is True


def test_repository_config_file_is_valid() -> None:
    settings = load_settings(config_file=DEFAULT_CONFIG_FILE, env_file=None)
    assert settings.ollama_model == "qwen3:4b-instruct"
    assert settings.github_remote == "git@github.com:Wil-1302/Jarvis.git"


def test_toml_values_are_loaded(tmp_path: Path) -> None:
    config = tmp_path / "jarvis.toml"
    config.write_text('name = "Friday"\nollama_model = "llama3.2:3b"\n', encoding="utf-8")
    settings = load_settings(config_file=config, env_file=None)
    assert settings.name == "Friday"
    assert settings.ollama_model == "llama3.2:3b"


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "jarvis.toml"
    config.write_text('name = "Friday"\nollama_model = "llama3.2:3b"\n', encoding="utf-8")
    monkeypatch.setenv("JARVIS_NAME", "Edith")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:1.7b")
    settings = load_settings(config_file=config, env_file=None)
    assert settings.name == "Edith"
    assert settings.ollama_model == "qwen3:1.7b"


def test_dotenv_file_is_loaded_and_empty_values_ignored(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JARVIS_LANGUAGE=EN\nOLLAMA_MODEL=\nOLLAMA_HOST=localhost:11434\n", encoding="utf-8"
    )
    settings = load_settings(config_file=None, env_file=env_file)
    assert settings.language == "en"
    assert settings.ollama_model == "qwen3:4b-instruct"  # vacío -> se mantiene el defecto
    assert settings.ollama_host == "http://localhost:11434"


def test_unknown_toml_key_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "jarvis.toml"
    config.write_text('nmae = "typo"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="nmae"):
        load_settings(config_file=config, env_file=None)


def test_invalid_toml_is_rejected(tmp_path: Path) -> None:
    config = tmp_path / "jarvis.toml"
    config.write_text("name = \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="TOML"):
        load_settings(config_file=config, env_file=None)


def test_invalid_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_ENV", "staging")
    with pytest.raises(ConfigError):
        load_settings(config_file=None, env_file=None)


def test_permissions_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_ALLOW_SHELL", "true")
    monkeypatch.setenv("JARVIS_ALLOWED_PATHS", f'["{tmp_path.as_posix()}"]')
    settings = load_settings(config_file=None, env_file=None)
    assert settings.allow_shell is True
    assert settings.allowed_paths == [tmp_path]


def test_relative_paths_resolve_inside_workspace(make_settings, tmp_path: Path) -> None:
    settings = make_settings()
    assert settings.log_path == tmp_path / "logs" / "jarvis.log"
    settings.ensure_dirs()
    for name in ("logs", "memory", "projects", "research", "downloads"):
        assert (tmp_path / name).is_dir()


def test_safe_dump_masks_secret_fields() -> None:
    class SecretSettings(Settings):
        spotify_client_secret: str = "super-secret-value"
        api_key: str = ""

    dumped = SecretSettings(_env_file=None).safe_dump()
    assert dumped["spotify_client_secret"] == "***"
    assert dumped["api_key"] == ""  # vacío: nada que ocultar
    assert dumped["name"] == "Jarvis"


def test_env_example_only_documents_known_settings() -> None:
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    active = re.findall(r"^([A-Z_]+)=(.*)$", text, flags=re.MULTILINE)
    fields = Settings.model_fields
    known = {f"JARVIS_{name.upper()}" for name in fields} | {
        (field.alias or "").upper() for field in fields.values()
    }
    for key, value in active:
        assert key in known, f"{key} no corresponde a ningún ajuste"
        assert not re.search(r"(?i)key|token|secret|password", key) or not value
