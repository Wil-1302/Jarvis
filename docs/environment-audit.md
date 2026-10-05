# JARVIS-WIL — Auditoría del entorno

- **Fecha:** 2026-10-05
- **Workspace:** `C:\Jarvis` (vacío antes de esta auditoría; no es un repositorio git)
- **Método:** solo comandos de lectura (CIM/WMI, registro, `--version`, API pública de GitHub). No se instaló, modificó, borró ni clonó nada. Ollama **no** se arrancó.

---

## Actualización Fase 1 (2026-10-05)

Cambios aplicados al entorno durante la Fase 1:

| Cambio | Detalle |
|---|---|
| Repositorio git | `git init -b main` en `C:\Jarvis`; `origin = git@github.com:Wil-1302/Jarvis.git`. El remoto estaba vacío (sin ramas). La autenticación SSH funciona (`Hi Wil-1302!`, clave `~/.ssh/id_ed25519`) |
| FFmpeg 9.0.1 essentials | `winget install Gyan.FFmpeg.Essentials --scope user`. Binarios en `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin`, añadido al PATH de **usuario** (las terminales abiertas antes de la instalación no lo ven hasta reiniciarse) |
| Python 3.12.14 | Gestionado por uv (`%APPDATA%\uv\python\cpython-3.12-...`, ya estaba descargado). venv local en `C:\Jarvis\.venv`. El Python global 3.14 no se ha tocado |
| Ollama | Se arrancó con `ollama app.exe` (ya tenía acceso directo de inicio automático). Se descargó **`qwen3:4b-instruct`** (2,5 GB). `qwen2.5-coder:14b` se conserva |
| Dependencias Python | `pydantic-settings`, `httpx` y `pytest` (dev), solo en el venv del proyecto |

**Prueba del modelo:** clasificación de intención en JSON ("abre Spotify y pon Arctic Monkeys" → `open_app`, con los parámetros correctos). 100% en GPU, ~3,2 GB de VRAM con contexto 4096, **~650 ms en caliente y ~58 tokens/s**. La primera carga en frío tardó ~63 s.

**Nuevo hallazgo: Smart App Control está ACTIVADO** (`VerifiedAndReputablePolicyState = 1`). Bloqueó `ruff.exe` (binario sin firmar) con `WinError 4551`. Los lanzadores de uv (`pytest.exe`, `jarvis.exe`), Python, Ollama y FFmpeg sí funcionan. **Riesgo para la Fase 2:** binarios o DLL nativos sin firma ni reputación (p. ej. `piper.exe`, algunas extensiones nativas) podrían ser bloqueados. Desactivarlo es una decisión del usuario: en Windows 11 se hace desde Seguridad de Windows y puede no ser reversible sin reinstalar.

## 1. Sistema

| Elemento | Valor |
|---|---|
| SO | Windows 11 Pro 25H2, build 26200.9457, 64 bits |
| Equipo | Lenovo, modelo 83JC (portátil) |
| CPU | AMD Ryzen 7 7435HS: 8 núcleos y 16 hilos |
| RAM | 24 GB (2 × 12 GB DDR5-4800); ~15 GB libres en el momento de la auditoría |
| GPU | NVIDIA GeForce RTX 4050 Laptop GPU: **6141 MiB de VRAM** (~1,1 GB ya en uso por el escritorio y las apps), compute capability 8.9 |
| Driver NVIDIA | 591.66 (soporta CUDA hasta la 13.1) |
| CUDA Toolkit | **No instalado** (`nvcc` ausente, `CUDA_PATH` vacío). No hace falta: faster-whisper/ctranslate2 usan las librerías de los wheels `nvidia-cublas-cu12` y `nvidia-cudnn-cu12` |
| Disco C: | 361 GB en total, **79,3 GB libres** |
| Disco F: | 1,9 GB (extraíble, probablemente un USB) |
| GPU integrada | No aparece como controlador de vídeo aparte |

## 2. Software

| Herramienta | Versión | Ruta / notas |
|---|---|---|
| Windows PowerShell | 5.1.26100 | Es la única que hay. **PowerShell 7 (`pwsh`) no está instalado** |
| Python | **3.14.7** (la única versión instalada) | `%LOCALAPPDATA%\Programs\Python\Python314`. El `py` launcher solo lista la 3.14 |
| pip | 26.2.1 | Python global casi vacío (3 paquetes, entre ellos `uv`) |
| uv | 0.12.13 | Disponible: puede crear venvs con otra versión de Python **sin tocar la instalación global** |
| Node.js | 24.19.0 | `C:\Program Files\nodejs` |
| npm | 11.17.0 | Globales: `@anthropic-ai/claude-code@2.1.289`, `@google/gemini-cli@0.59.0`, `@openai/codex@0.154.0` |
| Git | 2.55.0.windows.5 | |
| GitHub CLI | 2.100.0 | **No ha iniciado sesión** (`gh auth status` → sin sesión) |
| Claude Code | 2.1.289 | Iniciado con login de suscripción (`~/.claude/.credentials.json`). No hay servidores MCP globales configurados |
| Ollama | cliente 0.34.2 | **Servicio no iniciado** (el puerto 11434 rechaza conexiones) |
| FFmpeg / ffprobe | **No instalado** | |
| winget | 1.29.380 | Disponible para instalar a nivel de usuario |
| choco / scoop / conda / micromamba / docker | No instalados | |
| WSL | **Error** `Wsl/0x80070570` ("archivo o directorio dañado o ilegible") | Ver Conflictos |
| VS Code | 1.138.0 | |
| Visual C++ Runtime 2022 | 14.51 (x86 y x64) | No hay Build Tools de VS: no se pueden compilar extensiones nativas de Python |
| Google Chrome | 154.0.8037.93 | `C:\Program Files\Google\Chrome` |
| Microsoft Edge | 154.0.4258.53 | |
| Spotify (escritorio) | 1.3.3.264 | `%APPDATA%\Spotify`. **Spicetify** está en el PATH (cliente modificado) |
| Otros en el PATH | PHP 8.3, Composer | No son relevantes para el proyecto |

### Configuración relevante
- Política de ejecución: `CurrentUser = RemoteSigned`
- Rutas largas (`LongPathsEnabled`): **activadas (1)**
- Modo desarrollador: no configurado
- Alias de la Microsoft Store en WindowsApps: hay stubs de `python.exe` y `python3.exe`. `python` resuelve primero a la 3.14 real, pero `python3` apunta al stub de la Store.

### PATH
**Usuario:** `~\.local\bin`, Python314 y `Scripts`, Python Launcher, WindowsApps, spicetify, `AppData\Roaming\npm`, Ollama, PHP (winget), Composer, VS Code.
**Máquina:** System32, Windows, Wbem, PowerShell v1.0, OpenSSH, Git\cmd, nodejs, GitHub CLI.

### Variables de entorno
- **No existen** `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OLLAMA_*`, `CUDA_PATH`, `HF_*` ni `PICOVOICE_*`.
- Solo están las variables `CLAUDE_CODE_*` / `CLAUDECODE` de la sesión actual de Claude Code. Son temporales: no deben heredarse a procesos hijos de JARVIS.

### Procesos
- `claude` (2 procesos): son la sesión actual de Claude Code.
- No hay procesos de `ollama`, `openclaw`, `jarvis`, `python` ni `spotify` en ejecución.

### Instalaciones previas
- **Jarvis:** ninguna, aparte del propio `C:\Jarvis`. Se buscó en el perfil, AppData, Program Files y C:\.
- **OpenClaw:** ninguna. No existe el comando `openclaw` ni `~/.openclaw`.

## 3. Audio

| Tipo | Dispositivo | Estado |
|---|---|---|
| Micrófono | **Varios micrófonos (Realtek(R) Audio)**: array integrado | **Activo**: es el único micrófono disponible ahora |
| Micrófono | Auriculares con micrófono (Alaxe Hands-Free), Bluetooth | No conectado |
| Micrófono | Auriculares con micrófono (Redmi Buds 6 Play Hands-Free), Bluetooth | No conectado |
| Micrófono | Micrófono (Realtek), jack | No conectado |
| Captura | Mezcla estéreo (Realtek) | Deshabilitada |
| Salida | **Altavoces (Realtek(R) Audio)** | **Activa** |
| Salida | Auriculares Alaxe, Redmi Buds 6 Play, CN-S6737AC, jack Realtek | No conectados |
| Salida | PC Monitor / NVIDIA Output (HDMI) | No presentes |
| Virtual | Nahimic VAD, Nahimic mirroring, Nahimic Easy Surround | Instalados (software de audio de Lenovo) |

- Privacidad del micrófono: **Permitido** en general y para las apps de escritorio (`NonPackaged = Allow`).
- El micrófono principal es el array integrado del portátil, que está muy cerca de los altavoces. Hará falta cancelación de eco y la opción de interrumpir a JARVIS mientras habla.

## 4. IA y modelos disponibles

| Proveedor | Estado |
|---|---|
| Ollama (local) | Instalado, pero el servicio está parado. Solo hay un modelo descargado: **`qwen2.5-coder:14b`** (~8,4 GB en disco). **No cabe en los 6 GB de VRAM**: correría a medias en la CPU, lento |
| Claude Code (suscripción) | Funciona y tiene sesión iniciada. Admite modo headless (`claude -p`, `--output-format stream-json`) |
| API de Anthropic | No hay API key configurada |
| Gemini CLI / Codex CLI | Instalados como alternativas; no se comprobó la autenticación |
| STT/TTS locales (Whisper, Piper, etc.) | Ninguno instalado |

**Presupuesto de VRAM (orientativo):** de unos ~4,9 GB útiles salen faster-whisper (`small`/`medium` int8 ≈ 0,5–1,5 GB) más un LLM local de enrutado de ~3–4B cuantizado (≈ 2,5–3 GB). Un LLM de 7–8B con Whisper en la GPU a la vez ya no cabe con holgura.

## 5. Repositorios analizados (solo lectura remota, sin clonar)

| Repo | Lenguaje / tamaño | Licencia | Plataforma | Resumen |
|---|---|---|---|---|
| **isair/jarvis** (v2.5.0, 2026-10-04, ~1,9k ★) | Python | **No comercial**; las obras derivadas deben mantener la misma licencia | Win/macOS/Linux (desarrollado sobre todo en macOS) | Asistente de voz local: app de bandeja con PyQt6, faster-whisper (CUDA en Windows), webrtcvad, Piper/Chatterbox TTS, Ollama u otro servidor compatible con OpenAI, memoria con diario y grafo (faiss), enrutado de herramientas MCP, dictado por hotkey. La wake word se detecta por nombre dentro de la transcripción continua de Whisper. En Windows usa **Python 3.12** (micromamba) |
| **openclaw/openclaw** (~391k ★) | TypeScript (monorepo pnpm) | **MIT** | Gateway en Win nativo/WSL2/macOS/Linux; **Windows Hub** (app WinUI de bandeja) | Plano de control (Gateway) con sesiones, herramientas, skills, plugins, canales de chat y nodos. Tiene plugins de Ollama, Anthropic, Claude/Codex (harness), browser, MCP y TTS. **Voice wake solo en macOS/iOS/Android.** El Windows Hub levanta su Gateway dentro de una **distro WSL propia**. Requiere Node 24.16+ |
| **ethanplusai/jarvis** (~840 ★) | Python + TS | **Uso personal, no comercial** | **Solo macOS** (AppleScript) + Chrome | Voz para Claude Code: un "cerebro" `claude -p` persistente (con la suscripción, eliminando `ANTHROPIC_*` del entorno), brainstorm → spec → plan → ejecución con TDD, vigilancia de todas las sesiones de Claude Code, avisos por voz cuando una sesión necesita al usuario, runs en SQLite, memoria en Markdown y MCP configurable. STT con la Web Speech API de Chrome y TTS con Fish Audio (de pago) |
| **Julian-Ivanov/jarvis-voice-assistant** (~110 ★) | Python pequeño (~30 KB) | **Sin licencia** (no se puede reutilizar el código legalmente) | Windows | FastAPI + página web en Chrome (Web Speech API), Claude Haiku por API key, ElevenLabs, Playwright, captura de pantalla con Claude Vision, detector de doble aplauso (sounddevice) y colocación de ventanas con PowerShell/Win32 |

## 6. Conflictos y riesgos detectados

1. **Python 3.14 es la única versión.** Varias dependencias de voz (ctranslate2/faster-whisper, webrtcvad, torch, numpy<2, chatterbox) pueden no tener wheels para la 3.14 y no hay compiladores de C++. → Conviene usar un **venv del proyecto con Python 3.12 gestionado por `uv`**, sin tocar el Python global.
2. **WSL está roto** (`0x80070570`, archivo dañado). Bloquea la ruta recomendada de OpenClaw en Windows (el Gateway dentro de WSL). Para repararlo hace falta tocar el sistema (`wsl --update`, reinstalar la plataforma), así que necesita tu aprobación.
3. **OpenClaw no tiene wake word en Windows.** La parte de voz (wake word, STT y TTS) habrá que construirla nosotros en cualquier caso.
4. **El único modelo de Ollama (14B) no cabe en la VRAM** y el servicio está parado. Hace falta un modelo pequeño (3–4B) para clasificar intenciones con baja latencia.
5. **FFmpeg no está instalado** (lo necesitan Whisper y el procesado de audio).
6. **Licencias:** isair/jarvis y ethanplusai/jarvis son **no comerciales** (isair además obliga a mantener la licencia en derivados). Julian no tiene licencia. → Propongo **reimplementar los patrones**, sin copiar código, para que JARVIS-WIL quede libre de esas restricciones. OpenClaw (MIT) sí puede usarse directamente.
7. **Micrófono integrado junto a los altavoces y drivers Nahimic.** Hay riesgo de eco y de que JARVIS se escuche a sí mismo. Nahimic a veces altera el audio capturado. → Habrá que probar con y sin auriculares.
8. **Bluetooth (Alaxe, Redmi Buds):** al usar su micrófono pasan a perfil manos libres (HFP), con audio de 8–16 kHz y peor salida de sonido.
9. **Spotify:** para controlar la reproducción de forma fiable se necesita la **Web API de Spotify (requiere Premium y una app de desarrollador)**. La alternativa es usar URIs `spotify:` y teclas multimedia. Spicetify también podría servir como vía de control.
10. **`gh` sin sesión iniciada:** la API de GitHub sin autenticar tiene un límite de 60 peticiones por hora.
11. **Variables de Claude Code:** al lanzar `claude` desde JARVIS hay que limpiar las variables `CLAUDECODE` / `CLAUDE_CODE_*` heredadas y cualquier `ANTHROPIC_API_KEY` futura, que tendría prioridad sobre la suscripción.
12. **PowerShell 7 no está instalado.** No bloquea nada, pero algunos scripts de terceros esperan `pwsh`.
