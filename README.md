# JARVIS-WIL

Asistente personal de voz para Windows 11. Se activa con la palabra **"Jarvis"**, entiende
español, responde por voz y, en próximas fases, ejecutará acciones reales en el equipo.
Usa modelos locales (Ollama) para lo simple y Claude / Claude Code para lo complejo.

- **Repositorio oficial:** `git@github.com:Wil-1302/Jarvis.git` (https://github.com/Wil-1302/Jarvis)
- **Estado:** Fase 2 (motor de voz local) completada: conversación básica por voz, 100% local.
  Ver [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).
- **Uso:** personal y no comercial.

## Cómo funciona

```
Micrófono → wake word "Jarvis" (openWakeWord + Whisper) → VAD (Silero) → STT (faster-whisper, GPU)
         → Ollama qwen3:4b-instruct (streaming) → TTS Piper es_MX → altavoces → vuelve a escuchar
```

Detalles: [docs/voice.md](docs/voice.md) (voz, modelos, latencia, VRAM, Smart App Control) y
[docs/architecture.md](docs/architecture.md) (módulos y decisiones de diseño).

## Estructura

```
app/
  cli.py, __main__.py   CLI: python -m app [--voice | --health]
  config/               configuración central (pydantic-settings)
  core/                 JarvisCore (consola de texto), logging y health check
  audio/                dispositivos, captura, reproducción y análisis (python -m app.audio)
  voice/                wake word, VAD, STT, TTS, estados y pipeline (python -m app.voice)
  brain/                cliente Ollama y conversación
  tools/                herramientas de Windows, Spotify, navegador... (Fase 3)
  agents/               orquestación de Claude Code (Fase 6)
  ui/                   app de bandeja (Fase 4)
config/jarvis.toml      valores por defecto versionados (sin secretos)
tests/                  pytest (unitarios, integración y hardware)
scripts/                benchmark_stt.py, simulate_voice.py
docs/                   auditoría, plan, arquitectura y voz
models/                 modelos de voz descargados (no versionado)
projects/ research/     proyectos e investigación generados por JARVIS
logs/ memory/ downloads/  datos de ejecución (no versionados)
```

## Requisitos

| Herramienta | Versión verificada | Notas |
|---|---|---|
| Windows 11 x64 | 25H2 | Smart App Control activado (compatible) |
| GPU NVIDIA | RTX 4050 Laptop, 6 GB | opcional: sin GPU Whisper usa CPU |
| uv | 0.12.13 | gestiona Python 3.12 y el venv |
| Python | 3.12.14 (vía uv) | el Python global (3.14) no se toca |
| Ollama | 0.34.2 | modelo `qwen3:4b-instruct` |
| FFmpeg | 9.0.1 essentials (Gyan, winget) | |
| Git + SSH a GitHub | 2.55 | |
| Claude Code | 2.1.289 | necesario a partir de la Fase 6 |

## Instalación

```powershell
git clone git@github.com:Wil-1302/Jarvis.git C:\Jarvis
cd C:\Jarvis
uv sync                               # .venv con Python 3.12 + dependencias (uv.lock)
Copy-Item .env.example .env           # opcional: ajustes locales
ollama pull qwen3:4b-instruct
winget install --id Gyan.FFmpeg.Essentials --exact --scope user
uv run python -m app.voice --download-models   # ~1,7 GB: wake word, Whisper, voz Piper
```

## Activar el entorno

```powershell
.\.venv\Scripts\Activate.ps1   # o anteponer `uv run` a cada comando
```

## Ejecutar JARVIS

```powershell
python -m app --voice    # asistente de voz: di "Jarvis, ¿cómo estás?"
python -m app            # consola de texto
python -m app --health   # comprobación del entorno (código 0 = todo OK)
```

Pruebas por componente:

```powershell
python -m app.audio --devices
python -m app.audio --record-test
python -m app.voice --wake-test
python -m app.voice --vad-test
python -m app.voice --stt-test
python -m app.voice --tts-test
```

## Tests

```powershell
pytest                          # todos (unitarios + integración con modelos, Ollama, git)
pytest -m "not integration"     # solo unitarios: sin GPU, modelos ni servicios
$env:JARVIS_HARDWARE_TESTS=1; pytest -m hardware   # incluye grabar del micrófono
```

Los tests que necesitan tarjeta de sonido se omiten solos si no hay dispositivos (CI).

## Configuración

Prioridad: **variables de entorno > `.env` > `config/jarvis.toml` > valores por defecto**.
Las variables usan el prefijo `JARVIS_` (p. ej. `JARVIS_TTS_VOICE`), salvo `OLLAMA_HOST`,
`OLLAMA_MODEL` y `CLAUDE_COMMAND`. Consulta [.env.example](.env.example). `.env` nunca se versiona.

Ajustes: identidad (nombre, idioma, wake word), workspace, proveedor LLM, Ollama, Claude,
logging, permisos, dispositivos de audio, motor de wake word, VAD, Whisper, voz Piper y anti-eco.

## Dependencias

| Paquete | Para qué |
|---|---|
| `pydantic-settings` | configuración tipada desde TOML, `.env` y entorno |
| `httpx` | API de Ollama (incluido streaming) y descarga de modelos |
| `numpy`, `sounddevice` | audio (PortAudio) |
| `faster-whisper` (+ `ctranslate2`, `onnxruntime`) | STT; Silero VAD y openWakeWord en ONNX |
| `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` | CUDA 12 para Whisper sin instalar el CUDA Toolkit |
| `piper-tts` | TTS local |
| `pytest` (dev) | tests |
