"""Sin consultas a Hugging Face en cada arranque cuando los modelos ya están en caché.

Se importa ANTES que cualquier cosa que cargue huggingface_hub (faster-whisper, kokoro): si en la
caché están los archivos que usaremos (Whisper + Kokoro + la voz configurada), pone
HF_HUB_OFFLINE=1. Si falta algo, no toca nada y la primera carga descarga lo que haga falta.
JARVIS_HF_ONLINE=1 fuerza el modo en línea (para actualizar modelos).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_WHISPER_REPOS = {  # nombre corto de faster-whisper → repo (faster_whisper/utils.py)
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
}


def _cache_dir() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = os.environ.get("HF_HOME") or os.path.join(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"), "huggingface")
    return Path(home) / "hub"


def _has(repo: str, files: list[str]) -> bool:
    snaps = _cache_dir() / f"models--{repo.replace('/', '--')}" / "snapshots"
    return snaps.is_dir() and any(all((s / f).exists() for f in files) for s in snaps.iterdir())


def activate() -> bool:
    if os.environ.get("JARVIS_HF_ONLINE") == "1" or os.environ.get("HF_HUB_OFFLINE"):
        return os.environ.get("HF_HUB_OFFLINE") == "1"
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "config.yaml"))
    whisper = cfg["stt"]["model"]
    repo = _WHISPER_REPOS.get(whisper, whisper if "/" in whisper else None)
    ok = repo is not None and _has(repo, ["model.bin", "config.json", "tokenizer.json"])
    if cfg["tts"].get("engine", "kokoro") == "kokoro":
        ok = ok and _has("hexgrad/Kokoro-82M", ["config.json", "kokoro-v1_0.pth", f"voices/{cfg['tts']['voice']}.pt"])
    if ok:
        os.environ["HF_HUB_OFFLINE"] = "1"
        print("[Modelos] En caché: sin consultas a Hugging Face (JARVIS_HF_ONLINE=1 para actualizar).")
    else:
        print("[Modelos] Falta algún modelo en caché: se descargará en la primera carga.")
    return ok
