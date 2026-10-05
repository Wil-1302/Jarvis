"""Núcleo de JARVIS: ciclo de vida y manejo de entradas de texto.

En la Fase 1 solo confirma que el core funciona. Las intenciones, herramientas y
voz se conectarán aquí en fases posteriores.
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass

from app import __version__
from app.brain.ollama_client import OllamaClient, OllamaError
from app.config.settings import Settings
from app.core.logging import get_logger

log = get_logger("core")

GREETINGS = {"hello", "hi", "hola", "buenas", "hey"}
EXIT_COMMANDS = {"exit", "quit", "salir", "adios", "adiós"}
HELP_COMMANDS = {"help", "ayuda", "?"}
STATUS_COMMANDS = {"status", "estado"}


@dataclass
class CoreStatus:
    python: str
    ollama_connected: bool
    ollama_version: str | None
    model: str
    model_available: bool


@dataclass
class Reply:
    text: str
    exit: bool = False


class JarvisCore:
    def __init__(self, settings: Settings, ollama: OllamaClient | None = None) -> None:
        self.settings = settings
        self._ollama = ollama
        self.status: CoreStatus | None = None
        self.running = False

    @property
    def ollama(self) -> OllamaClient:
        if self._ollama is None:
            self._ollama = OllamaClient(self.settings.ollama_host, self.settings.ollama_timeout)
        return self._ollama

    def start(self) -> CoreStatus:
        log.info("Iniciando JARVIS-WIL v%s (%s)", __version__, self.settings.env)
        log.info("Python %s en %s", platform.python_version(), sys.executable)
        log.info("Configuración cargada: %s", self.settings.safe_dump())

        self.settings.ensure_dirs()
        log.info("Workspace listo: %s", self.settings.workspace)

        self.status = self._probe_ollama()
        self.running = True
        log.info("JARVIS core inicializado")
        return self.status

    def _probe_ollama(self) -> CoreStatus:
        version: str | None = None
        available = False
        try:
            version = self.ollama.version()
            available = self.ollama.has_model(self.settings.ollama_model)
            log.info(
                "Componente Ollama v%s inicializado (modelo %s: %s)",
                version,
                self.settings.ollama_model,
                "disponible" if available else "NO disponible",
            )
        except OllamaError as exc:
            log.warning("Ollama no disponible: %s", exc)
        return CoreStatus(
            python=platform.python_version(),
            ollama_connected=version is not None,
            ollama_version=version,
            model=self.settings.ollama_model,
            model_available=available,
        )

    def handle(self, text: str) -> Reply:
        # PowerShell 5.1 antepone un BOM al redirigir texto a stdin.
        command = text.replace("﻿", "").strip().lower().strip("!¡?¿.,")
        if not command:
            return Reply("")
        log.debug("Entrada recibida (%d caracteres)", len(text))

        if command in EXIT_COMMANDS:
            return Reply(f"Hasta luego. {self.settings.name} se desconecta.", exit=True)
        if command in GREETINGS:
            return Reply(f"Hola. Soy {self.settings.name}; el core está funcionando correctamente.")
        if command in HELP_COMMANDS:
            return Reply("Comandos disponibles: hola, estado, ayuda, salir.")
        if command in STATUS_COMMANDS:
            return Reply(self._describe_status())
        return Reply(
            "Core operativo. Todavía no tengo herramientas ni razonamiento conectados "
            "(llegarán en próximas fases)."
        )

    def _describe_status(self) -> str:
        status = self.status or self._probe_ollama()
        ollama = (
            f"conectado (v{status.ollama_version})" if status.ollama_connected else "desconectado"
        )
        model = "disponible" if status.model_available else "no disponible"
        return (
            f"Entorno {self.settings.env}, Python {status.python}, Ollama {ollama}, "
            f"modelo {status.model} {model}."
        )

    def shutdown(self) -> None:
        if self._ollama is not None:
            self._ollama.close()
            self._ollama = None
        if self.running:
            log.info("JARVIS core detenido")
        self.running = False
