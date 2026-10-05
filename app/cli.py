"""CLI de JARVIS-WIL.

    python -m app            consola interactiva
    python -m app --health   comprobación del entorno
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from app import __version__
from app.config.settings import ConfigError, Settings, load_settings
from app.core.health import format_results, is_healthy, run_health_checks
from app.core.jarvis import CoreStatus, JarvisCore
from app.core.logging import get_logger, setup_logging

log = get_logger("cli")


def _configure_stdio() -> None:
    # La consola de Windows puede no usar UTF-8; evita errores con acentos.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS-WIL")
    parser.add_argument("--health", action="store_true", help="comprueba el entorno y sale")
    parser.add_argument("--version", action="version", version=f"JARVIS-WIL {__version__}")
    return parser


def banner(settings: Settings, status: CoreStatus) -> str:
    line = "=" * 32
    ollama = "connected" if status.ollama_connected else "NOT CONNECTED"
    model = status.model if status.model_available else f"{status.model} (no disponible)"
    return "\n".join(
        [
            line,
            "JARVIS-WIL".center(32),
            line,
            "",
            f"Environment: {settings.env}",
            f"Python: {status.python}",
            f"Ollama: {ollama}",
            f"Model: {model}",
            "",
            "JARVIS core initialized successfully.",
            "Escribe 'ayuda' para ver los comandos o 'salir' para terminar.",
        ]
    )


def run_health(settings: Settings) -> int:
    log.info("Health check solicitado")
    results = run_health_checks(settings)
    print(format_results(results))
    healthy = is_healthy(results)
    print()
    print("Resultado: todo correcto." if healthy else "Resultado: hay comprobaciones en FAIL.")
    for result in results:
        log.info("Health %s: %s - %s", result.status.value, result.name, result.detail)
    return 0 if healthy else 1


def run_repl(
    settings: Settings,
    core: JarvisCore | None = None,
    input_fn: Callable[[str], str] = input,
) -> int:
    core = core or JarvisCore(settings)
    try:
        status = core.start()
        print(banner(settings, status))
        while True:
            try:
                text = input_fn("\nJARVIS > ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            reply = core.handle(text)
            if reply.text:
                print(reply.text)
            if reply.exit:
                break
    except Exception:
        log.exception("Error no controlado en la consola")
        raise
    finally:
        core.shutdown()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    setup_logging(settings)
    log.info("CLI iniciada (args=%s)", list(argv) if argv is not None else sys.argv[1:])
    try:
        return run_health(settings) if args.health else run_repl(settings)
    finally:
        log.info("CLI finalizada")
