# Plan de fases: JARVIS

Leyenda: `[x]` hecho · `[ ]` pendiente. Una fase a la vez: cada una necesita la aprobación del usuario antes de empezar.

## Fase 1: Montaje ✅ (2026-11-11)

- [x] Verificar requisitos: git 2.55, uv 0.12.13 y Ollama 0.34.2 están bien. Python 3.11 faltaba y se instaló con uv. WSL2 da error (ver Fase 2)
- [x] Revisar todo el historial antiguo en busca de secretos: no hay ninguno real (solo cadenas falsas en tests)
- [x] Crear el tag `jarvis-wil-v1` con la versión anterior y commitear el borrado de JARVIS-WIL
- [x] `CLAUDE.md` con la sección "Repo"
- [x] `face/` con `git subtree --squash` desde PanPenek/JarvisAi `main` (9dcf62b), `face/.python-version` = 3.11 y `face/CREDITS.md`
- [x] `brain/openclaw` como submodule superficial de solo lectura
- [x] Estructura (`brain/agent`, `brain/config`, `skills`, `mcp`, `scripts`, `docs`), `.gitignore`, `.env.example` y `README.md`
- [x] `docs/ANALISIS_FACE.md`
- [x] `docs/PLAN.md` y `docs/DECISIONES.md`
- [ ] Push a `origin/main` (pendiente de la aprobación del usuario)

## Fase 2: Cerebro (OpenClaw en WSL2)

- [ ] **Reparar WSL2 (lo hace el usuario, en una consola de administrador).** `wsl -l -v` falla con `Wsl/0x80070570` y no hay ninguna distro registrada. El error ya aparecía en la auditoría del 2026-10-05.
  1. `wsl --shutdown`
  2. `wsl --update` (si falla: `wsl --update --web-download`)
  3. `wsl --install -d Ubuntu-24.04` y crear el usuario de Linux (puede pedir reinicio)
  4. Si el error persiste: `chkdsk C: /scan` (solo lectura) y volver a evaluar
  5. Comprobar: `wsl -l -v` debe mostrar Ubuntu-24.04 en VERSION 2
- [ ] Instalar Node 24 dentro de WSL2
- [ ] Instalar OpenClaw desde su paquete oficial y hacer el onboarding
- [ ] Crear el agente `jarvis` (`brain/agent/SOUL.md`, `AGENTS.md`)
- [ ] Plantilla de configuración en `brain/config/` (sin tokens)
- [ ] Activar `gateway.http.endpoints.chatCompletions.enabled: true`, auth por token, solo loopback
- [ ] Probar con curl desde PowerShell (`GET /v1/models`, `POST /v1/chat/completions`)
- [ ] Si localhost no llega a WSL2: documentar la solución (modo de red `mirrored`)
- [ ] `scripts/sync-brain.ps1`, `scripts/doctor.ps1`

## Fase 3: Puente (face → OpenClaw)

- [ ] Proveedor `openclaw` en `face/config.yaml` (`base_url http://127.0.0.1:18789/v1`, token desde `.env`, `user` estable)
- [ ] Adaptar `main.py` según `docs/ANALISIS_FACE.md` §6 (no reenviar el historial local, timeout, sin fallback silencioso)
- [ ] Endurecer face: HUD en `127.0.0.1` y que la API no devuelva claves
- [ ] Probar la opción (A): tools locales desactivadas y OpenClaw hace todo (Windows-MCP por HTTP)
- [ ] Probar la opción (B): tools de face como function tools, ejecutadas en Windows
- [ ] Registrar la decisión en `docs/DECISIONES.md`
- [ ] Instalar las dependencias de face en `face/.venv` (Python 3.11) y comprobar Smart App Control con openwakeword

## Fase 4: Personalidad y voz

- [ ] STT en español (hoy `language="en"` está fijo en `stt.py`)
- [ ] Listar las voces de Kokoro instaladas (masculinas británicas `bm_*` para inglés; `em_*`/`ef_*` para español) y elegir una
- [ ] TTS: `lang_code` configurable (hoy `"a"` está fijo en `tts.py`)
- [ ] Wake word con pronunciación española (ver las lecciones de JARVIS-WIL en DECISIONES.md)
- [ ] Persona Jarvis: formal, breve, ingenioso, llama al usuario "señor"
- [ ] Estados escuchando / pensando / hablando en el HUD

## Fase 5: Cambio de cerebro

- [ ] Comando de voz "Jarvis, usa Claude / GPT / Gemini / modo local"
- [ ] Enviar `x-openclaw-model` o cambiar el modelo del agente
- [ ] Mostrar el cerebro activo en el HUD

## Fase 6: Cuerpo (MCP), uno por uno, cada uno con su prueba

- [ ] Windows-MCP (CursorTouch)
- [ ] Spotify (requiere Premium para controlar la reproducción)
- [ ] Office-Word-MCP-Server (GongRzhe)
- [ ] Google Calendar (nspady/google-calendar-mcp)
- [ ] GitHub MCP oficial
- [ ] Render MCP oficial
- [ ] AWS (awslabs/mcp o su sucesor)
- [ ] Packet Tracer (Mats2208)

## Fase 7: Skills propias

- [ ] (a) Flujo web: requisitos → construir → abrir en el navegador → "Señor, ¿está bien o cambiamos algo?" → destino (GitHub / Render / AWS) → desplegar tras confirmación
- [ ] (b) Horario → calendario: leer imagen o PDF → proponer eventos → preguntar si se repiten (esta semana / N semanas / indefinido) → crear tras confirmación
