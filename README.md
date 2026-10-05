# JARVIS-WIL

Asistente personal de voz para Windows 11. Funcionará en segundo plano, se activará con la palabra
**"Jarvis"**, entenderá órdenes en español y ejecutará acciones reales en el equipo. Usará modelos
locales (Ollama) para lo simple y Claude / Claude Code para lo complejo.

- **Repositorio oficial:** `git@github.com:Wil-1302/Jarvis.git` (https://github.com/Wil-1302/Jarvis)
- **Estado:** Fase 1 (cimientos) completada. Todavía no hay voz. Ver [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).
- **Uso:** personal y no comercial.

## Arquitectura actual (Fase 1)

```
python -m app ──► app/cli.py ──► app/core/jarvis.py (JarvisCore)
                     │                 │
                     │                 └─► app/brain/ollama_client.py ──► Ollama (qwen3:4b-instruct)
                     │
                     └─ --health ──► app/core/health.py (Python, config, workspace, Ollama,
                                     modelo, FFmpeg, Git, GitHub SSH, Claude Code)

app/config/settings.py   configuración central: entorno > .env > config/jarvis.toml > defaults
app/core/logging.py      logs/jarvis.log (rotativo) con redacción de secretos
```

Arquitectura objetivo: Voice UI → wake word → STT → JARVIS Core → orquestador → herramientas/MCP →
Windows / navegador / Spotify / ficheros / Internet → Claude Code / Ollama.

## Estructura

```
app/
  cli.py, __main__.py   entrada de la CLI (python -m app)
  config/               configuración central (pydantic-settings)
  core/                 JarvisCore, logging y health check
  brain/                clientes LLM (Ollama; Claude en fases posteriores)
  audio/ voice/         captura de audio, wake word, STT y TTS (Fase 2)
  tools/                herramientas de Windows, Spotify, navegador... (Fase 3)
  agents/               orquestación de Claude Code (Fase 6)
  ui/                   app de bandeja (Fase 4)
config/jarvis.toml      valores por defecto versionados (sin secretos)
tests/                  pytest (unitarios + integración)
scripts/                utilidades (vacío por ahora)
docs/                   auditoría del entorno y plan del proyecto
projects/ research/     proyectos e investigación generados por JARVIS
logs/ memory/ downloads/  datos de ejecución (no versionados; se crean al arrancar)
```

Cambios respecto a la propuesta inicial: el paquete Python se llama `app/` en la raíz del
repositorio (no hay una carpeta `JARVIS-WIL/` intermedia) para que `python -m app` funcione desde la raíz.
La CLI vive en `app/cli.py`, porque `app/ui/` queda reservado para la app de bandeja.

## Requisitos

| Herramienta | Versión verificada | Notas |
|---|---|---|
| Windows 11 x64 | 25H2 | |
| uv | 0.12.13 | gestiona Python 3.12 y el venv |
| Python | 3.12.14 (vía uv) | el Python global (3.14) no se toca |
| Ollama | 0.34.2 | modelo `qwen3:4b-instruct` |
| FFmpeg | 9.0.1 essentials (Gyan, winget) | |
| Git + SSH a GitHub | 2.55 | |
| Claude Code | 2.1.289 | opcional para el core; necesario en la Fase 6 |

## Instalación

```powershell
git clone git@github.com:Wil-1302/Jarvis.git C:\Jarvis
cd C:\Jarvis
uv sync                      # crea .venv con Python 3.12 e instala dependencias (uv.lock)
Copy-Item .env.example .env  # opcional: ajustes locales
ollama pull qwen3:4b-instruct
winget install --id Gyan.FFmpeg.Essentials --exact --scope user
```

## Activar el entorno

```powershell
.\.venv\Scripts\Activate.ps1   # o anteponer `uv run` a cada comando sin activar
```

## Ejecutar JARVIS

```powershell
python -m app            # consola interactiva (o: uv run python -m app / jarvis)
python -m app --health   # comprobación del entorno; código de salida 0 = todo OK
python -m app --version
```

Comandos de la consola: `hola`, `estado`, `ayuda` y `salir`.

## Tests

```powershell
pytest                    # todos (incluye integración con Ollama, git y GitHub)
pytest -m "not integration"   # solo tests unitarios, sin servicios externos
```

## Configuración

Prioridad: **variables de entorno > `.env` > `config/jarvis.toml` > valores por defecto**.
Las variables usan el prefijo `JARVIS_` (p. ej. `JARVIS_LANGUAGE`), salvo `OLLAMA_HOST`,
`OLLAMA_MODEL` y `CLAUDE_COMMAND`. Consulta [.env.example](.env.example). `.env` nunca se versiona.

Ajustes disponibles: nombre, idioma, wake word, entorno, workspace, proveedor LLM
(`hybrid` / `ollama` / `claude`), host, modelo y timeout de Ollama, comando de Claude, logging
(nivel, fichero, rotación), permisos (`allow_shell`, `allow_file_write`, `require_confirmation`,
`allowed_paths`) y opciones del health check.

## Dependencias

| Paquete | Para qué |
|---|---|
| `pydantic-settings` | configuración tipada y validada desde TOML, `.env` y entorno (incluye `pydantic` y `python-dotenv`) |
| `httpx` | cliente HTTP para la API de Ollama (testeable con `MockTransport`) |
| `pytest` (dev) | tests |

La CLI, el logging y TOML usan la biblioteca estándar (`argparse`, `logging`, `tomllib`).
