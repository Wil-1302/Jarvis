"""Health check del entorno de JARVIS (``python -m app --health``)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.brain.ollama_client import OllamaClient, OllamaError
from app.config.settings import Settings


class Status(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    detail: str


def _run(cmd: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def check_python(settings: Settings) -> CheckResult:
    version = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info[:2] != (3, 12):
        return CheckResult("Python", Status.FAIL, f"{version}: se requiere 3.12 (usa 'uv run')")
    in_venv = sys.prefix != sys.base_prefix
    where = f"venv {sys.prefix}" if in_venv else "fuera de un venv"
    return CheckResult("Python", Status.OK if in_venv else Status.WARN, f"{version} ({where})")


def check_config(settings: Settings) -> CheckResult:
    return CheckResult(
        "Configuración",
        Status.OK,
        f"env={settings.env}, idioma={settings.language}, wake word='{settings.wake_word}', "
        f"proveedor={settings.llm_provider}",
    )


def check_workspace(settings: Settings) -> CheckResult:
    workspace = settings.workspace
    if not workspace.is_dir():
        return CheckResult("Workspace", Status.FAIL, f"{workspace} no existe")
    try:
        settings.ensure_dirs()
        with tempfile.TemporaryFile(dir=workspace):
            pass
    except OSError as exc:
        return CheckResult("Workspace", Status.FAIL, f"{workspace} no es escribible: {exc}")
    return CheckResult("Workspace", Status.OK, str(workspace))


def check_ollama(settings: Settings) -> CheckResult:
    try:
        with OllamaClient(settings.ollama_host, timeout=5) as client:
            version = client.version()
    except OllamaError as exc:
        return CheckResult(
            "Ollama", Status.FAIL, f"{settings.ollama_host}: {exc}. ¿Está abierta la app Ollama?"
        )
    return CheckResult("Ollama", Status.OK, f"v{version} en {settings.ollama_host}")


def check_model(settings: Settings) -> CheckResult:
    name = f"Modelo {settings.ollama_model}"
    try:
        with OllamaClient(settings.ollama_host, timeout=5) as client:
            available = client.has_model(settings.ollama_model)
    except OllamaError as exc:
        return CheckResult(name, Status.FAIL, str(exc))
    if not available:
        return CheckResult(
            name, Status.FAIL, f"no descargado. Ejecuta: ollama pull {settings.ollama_model}"
        )
    return CheckResult(name, Status.OK, "disponible")


def _command_version(label: str, executable: str, args: list[str]) -> CheckResult:
    path = shutil.which(executable)
    if path is None:
        return CheckResult(label, Status.FAIL, f"'{executable}' no está en el PATH")
    try:
        result = _run([path, *args])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(label, Status.FAIL, f"{path}: {exc}")
    first_line = (result.stdout or result.stderr).strip().splitlines()[:1]
    if result.returncode != 0 or not first_line:
        return CheckResult(label, Status.FAIL, f"{path} devolvió código {result.returncode}")
    return CheckResult(label, Status.OK, first_line[0].split(" Copyright")[0])


def check_ffmpeg(settings: Settings) -> CheckResult:
    return _command_version("FFmpeg", settings.ffmpeg_path, ["-version"])


def check_claude(settings: Settings) -> CheckResult:
    result = _command_version("Claude Code", settings.claude_command, ["--version"])
    # No es imprescindible para el core: se degrada a WARN.
    if result.status is Status.FAIL:
        return CheckResult(result.name, Status.WARN, result.detail)
    return result


def check_git(settings: Settings) -> CheckResult:
    version = _command_version("Git", "git", ["--version"])
    if version.status is not Status.OK:
        return version
    git = shutil.which("git") or "git"
    cwd = str(settings.workspace)
    if _run([git, "-C", cwd, "rev-parse", "--is-inside-work-tree"]).returncode != 0:
        return CheckResult("Git", Status.FAIL, f"{cwd} no es un repositorio git")
    origin = _run([git, "-C", cwd, "remote", "get-url", "origin"]).stdout.strip()
    if origin != settings.github_remote:
        found = origin or "sin origin"
        return CheckResult(
            "Git", Status.FAIL, f"origin = {found}; se esperaba {settings.github_remote}"
        )
    return CheckResult("Git", Status.OK, f"{version.detail}; origin = {origin}")


def check_github(settings: Settings) -> CheckResult:
    if not settings.check_github:
        return CheckResult("GitHub SSH", Status.SKIP, "desactivado (JARVIS_CHECK_GITHUB=false)")
    if not settings.github_remote.startswith("git@"):
        return CheckResult("GitHub SSH", Status.SKIP, "el remoto no usa SSH")
    ssh = shutil.which("ssh")
    if ssh is None:
        return CheckResult("GitHub SSH", Status.FAIL, "'ssh' no está en el PATH")
    host = settings.github_remote.split(":", 1)[0]
    try:
        result = _run(
            [ssh, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host], timeout=20
        )
    except subprocess.TimeoutExpired:
        return CheckResult("GitHub SSH", Status.FAIL, "tiempo de espera agotado")
    output = (result.stdout + result.stderr).strip()
    # GitHub responde con código 1 aunque la autenticación sea correcta.
    if "successfully authenticated" in output:
        user = output.split("Hi ", 1)[-1].split("!", 1)[0]
        return CheckResult("GitHub SSH", Status.OK, f"autenticado como {user}")
    return CheckResult("GitHub SSH", Status.FAIL, output.splitlines()[-1] if output else "sin respuesta")


def check_audio(settings: Settings) -> CheckResult:
    try:
        from app.audio.device_manager import AudioDeviceError, check_settings, find_device
    except OSError as exc:  # PortAudio no disponible
        return CheckResult("Audio", Status.FAIL, f"sounddevice/PortAudio: {exc}")
    try:
        mic = find_device("input", settings.audio_input_device, settings.audio_host_api)
        check_settings(mic, "input", 16000, 1)
        speakers = find_device("output", settings.audio_output_device, settings.audio_host_api)
    except AudioDeviceError as exc:
        return CheckResult("Audio", Status.FAIL, str(exc))
    return CheckResult("Audio", Status.OK, f"mic '{mic.name}' (16 kHz) | altavoces '{speakers.name}'")


def check_voice_models(settings: Settings) -> CheckResult:
    from app.voice import models

    root = settings.models_path
    expected = {
        "wake word": models.wakeword_dir(root) / f"{settings.wake_model}.onnx",
        "Piper": models.piper_voice_paths(root, settings.tts_voice)[0],
        "Whisper": models.whisper_dir(root, settings.stt_model) / "model.bin",
        "Silero VAD": models.silero_vad_path(),
    }
    missing = [name for name, path in expected.items() if not path.is_file()]
    if missing:
        return CheckResult(
            "Modelos de voz",
            Status.FAIL,
            f"faltan: {', '.join(missing)}. Ejecuta: python -m app.voice --download-models",
        )
    return CheckResult(
        "Modelos de voz",
        Status.OK,
        f"{settings.wake_model}, whisper {settings.stt_model}, piper {settings.tts_voice}",
    )


def check_cuda(settings: Settings) -> CheckResult:
    if settings.stt_device == "cpu":
        return CheckResult("GPU (CUDA)", Status.SKIP, "STT configurado en CPU")
    try:
        from app.voice.stt import cuda_available

        available = cuda_available()
    except Exception as exc:
        return CheckResult("GPU (CUDA)", Status.WARN, f"no se pudo comprobar: {exc}")
    if not available:
        return CheckResult("GPU (CUDA)", Status.WARN, "sin GPU CUDA: Whisper usará CPU (más lento)")
    return CheckResult("GPU (CUDA)", Status.OK, "ctranslate2 detecta la GPU NVIDIA")


CHECKS: list[Callable[[Settings], CheckResult]] = [
    check_python,
    check_config,
    check_workspace,
    check_ollama,
    check_model,
    check_ffmpeg,
    check_git,
    check_github,
    check_claude,
    check_audio,
    check_voice_models,
    check_cuda,
]


def run_health_checks(
    settings: Settings, checks: list[Callable[[Settings], CheckResult]] | None = None
) -> list[CheckResult]:
    results = []
    for check in checks or CHECKS:
        try:
            results.append(check(settings))
        except Exception as exc:  # un check roto no debe tumbar el resto
            results.append(CheckResult(check.__name__, Status.FAIL, f"error inesperado: {exc}"))
    return results


def is_healthy(results: list[CheckResult]) -> bool:
    return all(result.status is not Status.FAIL for result in results)


def format_results(results: list[CheckResult]) -> str:
    width = max((len(result.name) for result in results), default=0)
    return "\n".join(
        f"[{result.status.value:<4}] {result.name:<{width}}  {result.detail}" for result in results
    )
