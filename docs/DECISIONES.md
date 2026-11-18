# Registro de decisiones

## D-001: Conservar el historial y el remoto (2026-11-11)

Se reutiliza el repo `git@github.com:Wil-1302/Jarvis.git` (**público**) en lugar de hacer `git init` desde cero.
La versión anterior (JARVIS-WIL) queda en el tag `jarvis-wil-v1` (commit `3f8d29c`) y su código se retira en un commit aparte.

Antes de reutilizar el repo se revisó todo el historial (los dos commits) en busca de secretos: archivos `.env`, `sk-`, `sk-ant-`,
`AIza`, `ghp_`/`github_pat_`, `AKIA`, `xox*-`, claves privadas y asignaciones de password/token/api_key.
**No hay secretos reales.** Solo aparecen cadenas falsas en `tests/test_logging.py`, que comprueban que el logger oculta secretos.
Nunca se commiteó un `.env`; `.env.example` solo tenía valores de configuración.

## D-002: face como subtree; OpenClaw como submodule de solo lectura (2026-11-11)

- `face/` se importa con `git subtree add --squash` desde `PanPenek/JarvisAi@main` (9dcf62b). Es nuestro código y se modifica libremente.
  Para traer cambios del original: `git subtree pull --prefix=face https://github.com/PanPenek/JarvisAi main --squash`.
- `brain/openclaw/` es un submodule **superficial** (`shallow = true`) de `openclaw/openclaw`, solo para consultar código y docs.
  No se edita. OpenClaw se instala desde su paquete oficial (~~en WSL2~~ nativo en Arch desde D-005) y se personaliza solo con configuración, el agente,
  skills propias y MCP. Así se puede actualizar con sus parches de seguridad sin conflictos.
- `face/.python-version` = `3.11`, para que face nunca use el Python 3.14 global.

## D-003: Licencia de face (2026-11-11)

El README de PanPenek/JarvisAi declara **MIT** (badge y sección "License"), pero **el repositorio no incluye un archivo LICENSE**.
Sin un texto de licencia explícito, la situación legal es ambigua: en rigor, el código queda bajo los derechos de autor por defecto.

Decisión del usuario: el repo sigue siendo público. Medidas:
- se conserva intacto el aviso MIT del `face/README.md` original;
- `face/CREDITS.md` reconoce al autor (PanPenek) y la URL original;
- se deja constancia aquí.

Pendiente opcional: abrir un issue en PanPenek/JarvisAi pidiendo que añada el archivo LICENSE.

Otras notas sobre el original:
- su README indica una URL de clonado incorrecta (`PanPenek/jarvis`); la buena es `PanPenek/JarvisAi`;
- dos de sus tres commits están firmados por `Antigravity <antigravity@openclaw.local>`, generados con IA;
- `PROJECT_SUMMARY.txt` lo describe como una versión "saneada y vendible" de un proyecto privado.

## D-004: Opción A vs. B para las tools de face — ✅ A (2026-11-17)
- **Resuelta:** opción A. face no ejecuta tools (sin pyautogui, run_python ni power_command); OpenClaw hace todo.
  Probado: "abre la calculadora de libreoffice" y la receta en .docx funcionan vía OpenClaw con allowlist.
  Medios y volumen también van por OpenClaw (`playerctl`/`wpctl` en la allowlist); si la latencia molesta, se revisa.

Pendiente (Bloque 6). Con todo en la misma máquina (D-005), el usuario prefiere la **opción A**: OpenClaw ejecuta
todas las acciones (shell + MCP) y face queda como voz + HUD. Se confirmará con una prueba real. Ver `docs/ANALISIS_FACE.md` §6.

## D-005: Migración a Arch Linux nativo (2026-11-16)

**Contexto:** WSL estaba corrupto (`Wsl/0x80070570`, nunca reparado) y el usuario migró el mismo PC de Windows a
Arch Linux nativo (Hyprland, Wayland). Detalle del entorno en `docs/ENTORNO_ARCH.md`.

**Decisión:**
- face y OpenClaw corren **nativos en Arch**, en la misma máquina, como **servicios systemd de usuario**
  (`loginctl enable-linger` para que el gateway viva sin sesión abierta).
- Desaparece la frontera Windows ↔ WSL2: no hay problemas de `localhost` entre sistemas ni modo de red `mirrored`.
- Repo en `~/Proyectos/Jarvis`. Scripts en bash (`scripts/*.sh`); lo que requiere root va en `scripts/arch/`
  y lo ejecuta el usuario.
- Quedan **obsoletos**: los scripts `.ps1`, `install.bat`/`start.bat`, Windows-MCP (CursorTouch), el OCR con PowerShell
  de face y todo lo relativo a Smart App Control. Se reemplazan por equivalentes Linux (wpctl, playerctl,
  brightnessctl, notify-send, wl-clipboard, ydotool y agent-sh/computer-use-linux) solo donde haga falta.
- Siguen vigentes: arquitectura cara/cerebro, "fusionar sin mezclar código", reglas de seguridad y
  los hallazgos de `docs/ANALISIS_FACE.md`.

**Consecuencia para la opción A/B (D-004):** como OpenClaw y el escritorio están en la misma máquina, OpenClaw puede
controlar el escritorio directamente (shell con aprobaciones + MCP), lo que hace natural la opción A.

## D-006: Node 26 del sistema en lugar de Node 24 LTS (2026-11-16)

La misión pedía Node 24 LTS. El sistema ya tiene `extra/nodejs` **26.13.1**, y OpenClaw (`package.json`
`engines.node: ">=24.16.0 <25 || >=26.1.0"`, `docs/install/node-compatibility.md`) marca Node 26 como **recomendado**
("arranque del gateway más rápido y menos memoria que Node 24"). Node 26 es además la línea LTS activa desde
octubre de 2026. Instalar `nodejs-lts-krypton` (24.22.3) obligaría a quitar `nodejs` 26, y mise/fnm añadiría otra capa.

**Decisión:** usar el `nodejs` 26 de los repos de Arch (se actualiza con `pacman -Syu`). npm global con prefijo `~/.local`.
Si OpenClaw dejara de soportar 26, el plan B es `nodejs-lts-krypton`.

---

## Lecciones de JARVIS-WIL (tag `jarvis-wil-v1`)

### Qué tenía

Un asistente propio en Python 3.12 (uv), escrito desde cero en unos 6.100 líneas con tests, en dos fases:
- **Fase 1**: base con configuración en pydantic-settings (`config/jarvis.toml` y `.env`), logging que oculta secretos,
  health check (Ollama, GPU, FFmpeg, GitHub) y CLI.
- **Fase 2**: pipeline de voz 100 % local:
  - wake word openWakeWord (ONNX vía onnxruntime) en modo híbrido con detección por transcripción;
  - VAD Silero (ONNX);
  - STT faster-whisper `large-v3-turbo` en la GPU;
  - LLM Ollama `qwen3:4b-instruct` con streaming;
  - TTS Piper `es_MX-ald-medium`;
  - máquina de estados `IDLE → WAKE_DETECTED → LISTENING → TRANSCRIBING → THINKING → SPEAKING`.
- **Sin tools, sin UI y sin integración con Claude.** Las fases 3 a 6 estaban planificadas pero no se hicieron.

### Qué funcionó

- **Python gestionado con uv** sin tocar el 3.14 global, con venv por proyecto.
- **Benchmark de STT con datos propios** (16 frases en español con ruido a 20 dB SNR, con el LLM cargado a la vez en la GPU):
  `large-v3-turbo` dio 22,1 % de WER con 0,30 s de latencia, mejor que `small` (31 %) y que `medium` (22,9 %, 0,34 s).
  `small`, que es lo que usa face por defecto, es claramente peor en español.
- **`stt_prompt`** con nombres propios ("Jarvis, Spotify, YouTube, Chrome.") corrigió errores del tipo "Harvies" → "Jarvis".
- **Filtrar las alucinaciones de Whisper** ("Gracias por ver el video.") y los segmentos con `no_speech_prob > 0.8`.
- **Anti-eco half-duplex**: micrófono silenciado mientras habla, 400 ms de margen, vaciar el búfer y reiniciar la wake word y el VAD.
  Eliminó los bucles de autoactivación con el micrófono integrado del portátil.
- **Logging que oculta secretos** y tests con dobles (fakes) del hardware de audio.
- **Trabajo por fases con aprobación**: auditoría del entorno solo con lectura antes de instalar nada.

### Qué falló o quedó pendiente

- **Smart App Control (activo)** bloqueó `_liblinear.pyd` de sklearn, que `openwakeword` importa, y también `ruff.exe`.
  Solución: ejecutar los ONNX de openWakeWord directamente con onnxruntime. **face usa `openwakeword.model.Model`, así que lo más probable es que le pase lo mismo.**
- **`hey_jarvis` no reconoce bien la pronunciación española**: daba puntuaciones de 0,03 a 0,20 con voces en español, frente a 0,92–0,99 con voces inglesas.
  Hubo que añadir la detección por transcripción (Whisper sobre cada frase, buscando "jarvis/yarvis/harvis..."), que gasta GPU continuamente.
  Falta entrenar un modelo propio.
- **Sin barge-in**: al ser half-duplex, no se puede interrumpir a Jarvis mientras habla. Hace falta AEC o auriculares.
- **GPU de 6 GB (RTX 4050 Laptop) compartida**: Whisper y Ollama caben justos, y `large-v3` completo no cabe. Si el usuario está jugando (Minecraft), la inferencia en la GPU va de 10 a 50 veces más lenta.
- **WSL ya estaba roto** (`Wsl/0x80070570`) en la auditoría del 2026-10-05 y nunca se reparó. Bloquea la Fase 2 actual.
- **PATH desactualizado** en las terminales abiertas antes de instalar FFmpeg: hay que reconstruir el PATH desde User y Machine.
- **Construir todo desde cero era lento**: dos fases después seguía sin tools ni UI. Por eso se pasa a reutilizar face (que ya trae tools y HUD) y OpenClaw (cerebro, MCP y skills).

### Qué se trae a la nueva arquitectura

1. ~~Comprobar Smart App Control al instalar face y tener preparado el plan B de onnxruntime para la wake word.~~
   **Obsoleto (plan B de Windows, D-005):** en Arch no hay Smart App Control. Aun así, se usarán los ONNX de openWakeWord
   con onnxruntime si el paquete `openwakeword` da problemas con Python 3.11.
2. En la Fase 4, usar `large-v3-turbo` (o medirlo de nuevo), `language="es"`, `stt_prompt` y el filtro de alucinaciones.
3. Planificar desde el principio la wake word para pronunciación española (modo híbrido o un modelo entrenado).
4. Mantener el anti-eco half-duplex. face tiene un cooldown de 2 s, pero no silencia el micrófono mientras habla.

## D-007: Aislamiento de rutas sensibles frente a OpenClaw (2026-11-17) — ⏸ propuesta
- **Contexto:** el gateway corre con el usuario `wil`; OpenClaw confina las tools de archivos al workspace, pero
  no puede impedir por rutas lo que haga `exec` en el host (lo dice su propia doc). Detalle y pruebas en
  `docs/AISLAMIENTO_OPENCLAW.md`.
- **Propuesta:** opción A = capa 1 (config de OpenClaw + allowlist de exec sin intérpretes ni `systemd-run`/`busctl`)
  + capa 2 (drop-in systemd con `InaccessiblePaths` sobre `~/.ssh`, `~/.gnupg`, llaveros, perfiles de navegadores,
  `~/CyberLab` y credenciales). Probado: bloquea lectura/escritura y mantiene el bus de sesión. Evasión conocida:
  `systemd-run --user` por el bus → se cierra exigiendo aprobación humana para esos comandos.
- **Alternativas:** B = sandbox Podman para exec; C = usuario del sistema `jarvis` separado (más fuerte, pierde el
  escritorio y necesita un puente).
- **Estado:** resuelta el 2026-11-17 por el usuario: capas 1 y 2 + refuerzos a-e (opción A). Aplicada (ver D-008).

## D-008: Cerebro Claude (login de Claude Code) + respaldo Codex; fuera Ollama y Gemini (2026-11-17)
- **Decisión del usuario:** sin Ollama ni API keys. Principal: Claude vía el runtime `claude-cli` de OpenClaw
  (usa el `claude` instalado y su login; OpenClaw no lee ni guarda esos tokens). Respaldo: ChatGPT/Codex OAuth.
- **Modelo:** `anthropic/claude-opus-5-5`. Se probó `claude-fable-5-2` (el nivel más alto del menú): con el plan Pro
  responde "You're out of usage credits" → exige créditos extra. Opus 5.5 sí funciona (~3 s en caliente).
- **Respaldo:** `openai/gpt-6-astra` (predeterminado de la suscripción Codex según la doc de OpenClaw).
- **Consecuencias:** se desinstalan `ollama`, `ollama-cuda` y `cuda` (5,4 GB); el script de sistema ya no los instala
  y los limpia. `~/.claude` y `~/.claude.json` no pueden bloquearse en el encierro (los necesita el CLI); se protegen
  con la capa 1 (fs solo en el workspace; exec por allowlist sin lectores genéricos ni intérpretes).
  El uso consume los límites de la suscripción Pro (la doc de OpenClaw lo advierte para `claude -p`).
- **Refuerzos a-e** (no se encontró una lista previa escrita; se definieron así):
  a) exec solo por allowlist (`on-miss` → aprobación humana; sin intérpretes, `systemd-run`, `busctl`, `ydotool`,
     `cat`/`cp`/`curl`), con `argPattern` por herramienta y `strictInlineEval`;
  b) `tools.elevated` desactivado, `tools.openclaw.autoApproveChanges: false`, tools `gateway`, `nodes`, `terminal`,
     `screen` y `browser` denegadas, control del navegador apagado;
  c) `tools.fs.workspaceOnly` y `applyPatch.workspaceOnly`;
  d) sin persistencia: `ReadOnlyPaths` para unidades systemd, autostart, Hyprland, shells, `~/.local/bin`,
     `node_modules` globales, `~/.local/share/{claude,applications}` y `scripts/` del repo;
  e) `NoNewPrivileges` (sin sudo/setuid para nada que lance el gateway), `RestrictSUIDSGID`, `UMask=0077`;
     además sesiones visibles solo por agente y agent-to-agent desactivado (recomendación de `security audit`).

## D-009: Audio de face: un micrófono compartido por PipeWire y ducking propio (2026-11-17)
- **Problema:** face no oía y la música se distorsionaba. PyAudio (wake word) y sounddevice (STT) abrían la fuente
  por defecto por pipewire-alsa: el micrófono de los audífonos BT (silenciado). Abrirlo pasaba los audífonos a
  HSP/HFP (mono 16 kHz) → música distorsionada. El micrófono del portátil estaba a +60 dB (saturado).
- **Decisión:** un solo `pw-record` (cliente nativo de PipeWire) con `--target` al micrófono del portátil, 16 kHz mono
  remuestreado en el stream y latencia de nodo 80 ms: el grafo sigue a 48 kHz y su quantum no cambia. Wake word y STT
  se suscriben al mismo flujo (`face/jarvis/mic.py`). Autoswitch BT de WirePlumber desactivado.
- **Ducking:** guardar y restaurar el volumen de cada sink-input (`face/jarvis/ducking.py`), al 20 % del que tenía.
  Descartado el ducking por roles de WirePlumber: exige enrutar todos los streams por sinks loopback por rol (cambia
  el grafo de todo el sistema). Estado en `$XDG_RUNTIME_DIR/jarvis/ducking.json` antes de tocar nada; lo deshacen el
  arranque y el `ExecStopPost` (también si face se cae). Si el usuario cambió un volumen entretanto, se respeta.
  La voz de JARVIS se llama `JARVIS`/`jarvis-voz` (`PIPEWIRE_PROPS` en run.sh) y no se baja.
  Límite conocido: si un programa se cierra mientras está bajado, WirePlumber puede recordar su 20 % la próxima vez.
- **Atajo:** Super+J (Hyprland) → `scripts/bin/jarvis-escucha` → socket Unix `$XDG_RUNTIME_DIR/jarvis/face.sock` (600).
