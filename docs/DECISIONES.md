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
  No se edita. OpenClaw se instala desde su paquete oficial en WSL2 y se personaliza solo con configuración, el agente,
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

## D-004: Opción A vs. B para las tools de face

Pendiente (Fase 3). Ver `docs/ANALISIS_FACE.md` §6.

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

1. Comprobar Smart App Control al instalar face y tener preparado el plan B de onnxruntime para la wake word.
2. En la Fase 4, usar `large-v3-turbo` (o medirlo de nuevo), `language="es"`, `stt_prompt` y el filtro de alucinaciones.
3. Planificar desde el principio la wake word para pronunciación española (modo híbrido o un modelo entrenado).
4. Mantener el anti-eco half-duplex. face tiene un cooldown de 2 s, pero no silencia el micrófono mientras habla.
