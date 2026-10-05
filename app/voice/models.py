"""Descarga y localización de los modelos de voz (todo queda en ``models/``, fuera de git).

- Wake word: modelos ONNX oficiales de openWakeWord (Apache-2.0, release v0.5.1).
- TTS: voces de Piper (rhasspy/piper-voices en Hugging Face).
- STT: modelos CTranslate2 de faster-whisper (Hugging Face).
- VAD: Silero VAD (MIT), incluido en el paquete faster-whisper.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from app.core.logging import get_logger

log = get_logger("voice.models")

OWW_RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
OWW_FEATURE_MODELS = ("melspectrogram.onnx", "embedding_model.onnx")
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def _download(url: str, target: Path) -> Path:
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    log.info("Descargando %s", url)
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        with partial.open("wb") as fh:
            for chunk in response.iter_bytes(1 << 20):
                fh.write(chunk)
    partial.replace(target)
    log.info("Guardado %s (%.1f MB)", target, target.stat().st_size / 1e6)
    return target


def wakeword_dir(models_dir: Path) -> Path:
    return models_dir / "openwakeword"


def ensure_wakeword_models(models_dir: Path, model_name: str) -> dict[str, Path]:
    folder = wakeword_dir(models_dir)
    files = {name: _download(f"{OWW_RELEASE}/{name}", folder / name) for name in OWW_FEATURE_MODELS}
    files["wakeword"] = _download(f"{OWW_RELEASE}/{model_name}.onnx", folder / f"{model_name}.onnx")
    return files


def piper_voice_paths(models_dir: Path, voice: str) -> tuple[Path, Path]:
    folder = models_dir / "piper"
    return folder / f"{voice}.onnx", folder / f"{voice}.onnx.json"


def ensure_piper_voice(models_dir: Path, voice: str) -> Path:
    """``voice`` con formato ``<lang>_<REGION>-<name>-<quality>``, p. ej. ``es_MX-ald-medium``."""
    lang_region, name, quality = voice.split("-")
    lang = lang_region.split("_")[0]
    base = f"{PIPER_BASE}/{lang}/{lang_region}/{name}/{quality}/{voice}"
    model, config = piper_voice_paths(models_dir, voice)
    _download(f"{base}.onnx.json", config)
    return _download(f"{base}.onnx", model)


def whisper_dir(models_dir: Path, size: str) -> Path:
    return models_dir / "whisper" / size


def ensure_whisper_model(models_dir: Path, size: str) -> Path:
    from faster_whisper.utils import download_model

    target = whisper_dir(models_dir, size)
    if (target / "model.bin").is_file():
        return target
    log.info("Descargando modelo Whisper '%s'", size)
    return Path(download_model(size, output_dir=str(target)))


def silero_vad_path() -> Path:
    import faster_whisper

    return Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"
