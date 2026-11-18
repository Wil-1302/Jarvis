# Plan: JARVIS en Arch Linux

Leyenda: `[x]` hecho · `[ ]` pendiente · ⏸ requiere al usuario. Detalle de cada bloque en `docs/MISION_ARCH.md`;
historial en `docs/BITACORA.md`.

## Histórico (Windows/WSL — obsoleto, ver D-005)

- Fase 1 (Montaje) ✅ 2026-11-11: monorepo, subtree de face, submodule de OpenClaw, ANALISIS_FACE, PLAN, DECISIONES.
- Fase 2 en adelante (WSL2) **abandonada**: WSL corrupto (`Wsl/0x80070570`). Se replanifica en los bloques siguientes.

## Bloque 0 — Auditoría ✅ (2026-11-16)
- [x] `docs/ENTORNO_ARCH.md`

## Bloque 1 — Documentación a Arch ✅ (2026-11-16)
- [x] CLAUDE.md reescrito para Arch
- [x] DECISIONES: D-005 (migración), D-006 (Node 26), plan B de Windows marcado obsoleto
- [x] PLAN.md replanificado

> **2026-11-17 — cambio de planes (D-008, MISION_ARCH):** sin Ollama ni Gemini; Claude (login de Claude Code)
> + respaldo Codex. Paradas solo para sudo, logins y pruebas de voz.

## Bloque 2 — Paquetes del sistema
- [x] `scripts/arch/01-sistema.sh` ejecutado el 2026-11-17 (instaló ollama-cuda por error de elección; linger lo activó Claude)
- [x] Script reescrito: sin Ollama/CUDA, los limpia si están, ufw siempre
- [x] Ejecutado de nuevo: ollama, ollama-cuda y cuda desinstalados; ufw instalado
- [ ] ⏸ ufw inactivo: el kernel en marcha (arch1-1) no tiene módulos (instalado arch1-2) → reiniciar y
      `sudo ufw --force enable && sudo systemctl enable --now ufw`

## Bloque 3 — Entorno de usuario
- [x] Python 3.11.18 (uv), prefijo npm `~/.local`, git, llave SSH
- [ ] ⏸ Pegar la llave correcta en GitHub (la registrada es otra) → `ssh -T` → remoto a SSH

## Bloque 4 — Ollama ❌ obsoleto (D-008)

## Bloque 5 — Cerebro: OpenClaw
- [x] Doc leída; OpenClaw 2026.11.5 por npm; submodule fijado en `v2026.11.5`
- [x] Onboarding no interactivo con `--auth-choice anthropic-cli` (reutiliza el login de Claude), loopback + token, sin canales
- [x] Servicio `openclaw-gateway.service` + encierro (drop-in se instala *después* de `gateway install`: si existe antes, falla)
- [x] Agente `jarvis` (SOUL/AGENTS/IDENTITY/USER), `scripts/sync-brain.sh`, token en `.env` (600)
- [x] Primary `anthropic/claude-opus-5-5` (Fable pide créditos extra en Pro); fallback `openai/gpt-6-astra`
- [x] chatCompletions; `/v1/models` y "hola" con curl (≈3 s en caliente); 401 sin token
- [x] Capa 1 + 2 + refuerzos a-e aplicados y probados; `security audit` 0 críticos
- [ ] ⏸ Login de ChatGPT: `openclaw models auth login --provider openai`
- [ ] Prueba de failover real (primary agotado → GPT) y aviso por voz en face

## Bloque 6 — Cara en Linux + puente
- [x] Endurecimiento: HUD solo en 127.0.0.1, token en cookie HttpOnly (HTTP + WS), Host/Origin locales,
      `/api/providers` sin keys, PUT/DELETE de proveedores desactivados; `power_command`/`run_python` fuera (opción A)
- [x] Opción A (D-004): face sin tools locales; las acciones las hace OpenClaw (probado con abrir app y documento)
- [x] `install.bat`/`start.bat` → `scripts/install-face.sh`, `face/run.sh`, `start-all.sh`, `stop-all.sh`, `doctor.sh`
- [x] venv 3.11 (torch CPU, cuBLAS/cuDNN por pip, sin /opt/cuda); Whisper large-v3-turbo en GPU (0,48 s),
      Kokoro em_alex en CPU (0,28 s), wake word ONNX (1,00 con "Hey Jarvis" sintético)
- [x] Puente `jarvis/brain.py` (sin historial, timeout 180 s, sin fallback silencioso, respaldo con aviso)
- [x] `jarvis-face.service` activo; prueba HUD → face → OpenClaw → Claude → voz por WebSocket
- [x] Tests: 23 en verde (puente, seguridad del HUD, STT)
- [x] Audio: un micrófono compartido por PipeWire, BT siempre en A2DP, ducking al 20 %, atajo Super+J, HF sin red (D-009)
- [x] Voz natural: activación por nombre (VAD + Whisper), conversación, respuestas locales, streaming (D-010)
- [x] Latencia Opus vs Sonnet → Sonnet principal (D-011)
- [ ] ⏸ Elegir voz (muestras en tmp/voces/) e integrarla
- [ ] ⏸ Prueba de voz con el señor: conversación de 3 turnos

## Bloque 7 — Voz y personalidad
- [ ] STT con idioma configurable (es por defecto); TTS con `lang_code` configurable
- [x] Muestras de voces en `tmp/voces/` (Kokoro, Piper, Edge)
- [ ] SOUL.md completo
- [~] HUD: espera / escuchando / pensando / hablando / en conversación (falta ejecutando + cerebro activo)
- [x] Wake word en español: sustituida por el nombre en la frase (D-010)

## Bloque 8 — Cambio de cerebro por voz
- [ ] "usa Claude / usa GPT" → `x-openclaw-model`, persistido y en el HUD (Gemini y local: obsoletos, D-008)

## Bloque 9 — MCP (⏸ OK antes de cada uno)
- [ ] 1. agent-sh/computer-use-linux (run_shell desactivado)
- [ ] 2. Spotify (cliente ya instalado) + marcelmarais/spotify-mcp-server + MPRIS
- [ ] 3. GongRzhe/Office-Word-MCP-Server + LibreOffice
- [ ] 4. nspady/google-calendar-mcp (⏸ OAuth)
- [ ] 5. GitHub MCP oficial (⏸ token)
- [ ] 6. Render MCP oficial (⏸ key)
- [ ] 7. AWS (⏸)
- [ ] 8. Packet Tracer + Mats2208/MCP-Packet-Tracer (⏸ descarga)

## Bloque 10 — Skills propias
- [x] Abrir aplicación (`jarvis-abrir`, probada por HTTP) · [x] Documento .docx (`jarvis-documento`, probada por HTTP)
- [ ] ⏸ Prueba de voz de ambas
- [ ] Música · [ ] Página web · [ ] Horario → calendario · [ ] Pendientes + resumen diario

## Terminado cuando
- [ ] `doctor.sh` en verde; gateway y face arrancan solos; voz: saludo, música, documento, cambio de cerebro, pendientes; docs al día; ⏸ push
