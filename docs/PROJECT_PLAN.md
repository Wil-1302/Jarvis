# JARVIS-WIL — Plan de proyecto (BORRADOR)

> Borrador vivo. Cada fase se aprueba por separado.
> Base: `docs/environment-audit.md` (2026-10-05).
> Repositorio oficial: `git@github.com:Wil-1302/Jarvis.git`

## Decisiones tomadas (2026-10-05)

| Tema | Decisión |
|---|---|
| Python del proyecto | 3.12 con `uv` (venv local); el Python global no se modifica |
| Wake word | `Jarvis` |
| Idioma | Español latino o neutro |
| Voz | Local/offline al principio |
| Cerebro | Híbrido: Ollama (`qwen3:4b-instruct`) para lo simple, Claude para lo complejo |
| Desarrollo | Claude Code como agente principal |
| WSL / OpenClaw | No reparar WSL ni instalar OpenClaw todavía |
| Spotify | Se integra más adelante |
| Licencia de uso | Personal y no comercial por ahora. No se copia código de repos con licencias restrictivas |

## Principios

- **Local primero:** la wake word, el STT y el TTS corren en la máquina. La nube (Claude) se usa para razonar o programar cuando aporte valor.
- **Aplicación de bandeja**, no una página web.
- **Nada global sin aprobación:** venv del proyecto (Python 3.12 vía `uv`); instalaciones a nivel de usuario.
- **Reimplementar patrones, no copiar código** de los repos con licencia no comercial (isair, ethanplusai) ni del que no tiene licencia (Julian). OpenClaw (MIT) sí se puede integrar.
- **Seguridad:** las acciones destructivas o externas requieren confirmación por voz. El contenido que llega de la web o de herramientas se trata como dato, nunca como instrucción.
- **Presupuesto de 6 GB de VRAM:** Whisper más un LLM pequeño en la GPU. El trabajo pesado va a Claude.

## Arquitectura propuesta

```
[Tray app (PySide6)]  estado · ajustes · logs · chat de respaldo
        │
[Audio I/O] mic → openWakeWord ("hey jarvis"/"jarvis") → VAD (Silero) → faster-whisper (GPU)
        │                                                     ▲
        ▼                                        barge-in / cancelación de eco
[JARVIS Core] (Python, asyncio)
   ├─ Router de intenciones: reglas rápidas + LLM pequeño (Ollama) → llamada a herramienta
   ├─ Registro de herramientas (internas + clientes MCP)
   ├─ Memoria (SQLite + Markdown)
   └─ Orquestador de tareas largas ──► Claude Code headless (`claude -p`, stream-json)
        │                                └─ (opcional, fase 7) OpenClaw Gateway
        ▼
[Herramientas] Windows (apps, ventanas, volumen) · Spotify · navegador (Playwright) · ficheros · web
        │
[TTS] Piper (voz en español, local) → altavoces
```

Qué tomamos de cada repo (ideas y patrones):
- **isair/jarvis:** pipeline de voz local (faster-whisper con CUDA y fallback a CPU, VAD, Piper, interrupción) y enrutado de MCP por subconjuntos para no saturar el contexto.
- **ethanplusai/jarvis:** orquestación de Claude Code (cerebro persistente, spec → plan → ejecución, runs en SQLite, vigilar sesiones, avisar solo cuando hace falta, limpieza del entorno `ANTHROPIC_*`).
- **Julian-Ivanov:** herramientas Windows (lanzar apps, colocar ventanas con Win32/PowerShell, Playwright, captura de pantalla).
- **OpenClaw:** candidato a orquestador o gateway en una fase posterior (skills, plugins, multi-agente, canales móviles). No aporta la parte de voz en Windows.

## Fases

### Fase 0 — Auditoría ✅
Inventario del entorno, análisis de los repos, este borrador.

### Fase 1 — Cimientos ✅ (2026-10-05)
- Repositorio git con `origin = git@github.com:Wil-1302/Jarvis.git`.
- Estructura `app/` (core, config, audio, voice, brain, tools, agents, ui), `pyproject.toml` y `uv.lock`.
- venv con Python 3.12.14 (uv). Dependencias: `pydantic-settings`, `httpx`, `pytest`.
- Configuración central (`config/jarvis.toml` + `.env` + entorno), incluidos los permisos.
- Logging en `logs/jarvis.log` (rotativo, con redacción de secretos).
- CLI `python -m app` y health check `python -m app --health` (9 comprobaciones).
- FFmpeg 9.0.1 (winget, usuario). Ollama con `qwen3:4b-instruct` probado.
- 53 tests (unitarios y de integración) en verde.
- Pendiente para el inicio de la Fase 2: el script de diagnóstico de audio, porque necesita `sounddevice`.

### Fase 2 — Motor de voz ✅ (2026-10-05)
- Smart App Control se mantiene activado. Bloqueó scikit-learn (dependencia de `openwakeword`) → modelos ONNX de openWakeWord ejecutados directamente.
- Audio (`python -m app.audio`), wake word híbrido (openWakeWord + nombre en la transcripción de Whisper), Silero VAD, faster-whisper `large-v3-turbo` en GPU, Piper `es_MX-ald-medium`, máquina de estados, pipeline con anti-eco y `python -m app --voice`.
- Latencia simulada: primer audio ~0,65 s tras el fin de la frase (~1,35 s percibidos).
- Detalle en `docs/voice.md`. Pendientes: barge-in/AEC, wake word propio entrenado en español, degradación automática si un juego ocupa la GPU.

Plan original de la fase:
- Captura con `sounddevice`, wake word con openWakeWord, VAD, STT con faster-whisper en español (comparar `small`, `medium` y `large-v3-turbo` en latencia y precisión) y TTS con Piper (voz es_ES o es_MX).
- Máquina de estados: `IDLE → WAKE → LISTENING → THINKING → SPEAKING → IDLE`.
- Interrupción (barge-in) y supresión de eco.
- **Objetivo:** menos de 1,5 s desde el fin de la frase hasta el inicio de la respuesta en comandos simples.

### Fase 3 — Core y herramientas de Windows
- Router de intenciones: reglas y patrones para comandos frecuentes, con un LLM local de respaldo que use tool calling.
- Herramientas: abrir y cerrar apps, volumen y multimedia, navegador, búsqueda web, ficheros (limitados a rutas permitidas), hora y clima.
- **Spotify:** Web API (si hay Premium) o URI más teclas multimedia.
- Confirmación por voz para las acciones de riesgo.
- **Demo objetivo:** "Jarvis, abre Spotify y reproduce Arctic Monkeys".

### Fase 4 — App de bandeja
- PySide6: icono con estados, menú, ajustes (micrófono, voz, modelos), visor de logs y chat de texto.
- Inicio automático (Task Scheduler o carpeta Startup, a nivel de usuario) y una sola instancia.

### Fase 5 — MCP, memoria e investigación
- Cliente MCP (stdio) con servidores configurables y selección de herramientas por petición.
- Memoria persistente (preferencias, proyectos).
- Investigación web: búsqueda, lectura de páginas, descarga de documentación a la carpeta del proyecto.

### Fase 6 — Orquestación de Claude Code ("Jarvis, crea un sistema de ventas")
- Diálogo de requisitos por voz → `docs/spec.md` y arquitectura en una carpeta nueva de proyecto.
- Lanzar `claude -p` en ese proyecto con un brief (plan → ejecución con TDD), leyendo los eventos `stream-json`.
- Bucle de pruebas, corrección y nuevas pruebas, con límites de tiempo, tokens y reintentos.
- Avisos por voz: progreso al llegar a cada hito, interrupción solo cuando se necesita una decisión o un permiso.
- Registro de runs (SQLite) y estado consultable por voz ("¿cómo va el proyecto?").

### Fase 7 — Integración con OpenClaw (opcional, a evaluar)
- Evaluar el Gateway nativo en Windows frente al de WSL y el Windows Hub (modo nodo y servidor MCP).
- Si aporta valor: JARVIS-WIL como "nodo de voz" y OpenClaw como orquestador multi-agente o canales (Telegram/WhatsApp para darle órdenes desde el móvil).

### Fase 8 — Endurecimiento y empaquetado
- Permisos por herramienta, auditoría de acciones, gestión de secretos (Windows Credential Manager).
- Empaquetado (PyInstaller o similar) e instalador de usuario.
- Pruebas automatizadas del pipeline (audio grabado → intención esperada).

## Decisiones pendientes para el usuario

1. ¿Spotify Premium? (determina el método de control en la Fase 3).
2. ¿Borrar los modelos Whisper `small` y `medium` del benchmark (~2 GB en `models/whisper`)?
3. ¿Voz masculina `es_MX-ald-medium` o femenina `es_MX-claude-high`?
