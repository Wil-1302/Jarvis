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

## Bloque 2 — Paquetes del sistema ⏸ sudo
- [ ] `scripts/arch/01-sistema.sh` (idempotente, con confirmación)
- [ ] ⏸ El usuario ejecuta `sudo bash scripts/arch/01-sistema.sh`

## Bloque 3 — Entorno de usuario
- [ ] `uv python install 3.11`
- [ ] Prefijo npm en `~/.local`
- [ ] git config global
- [ ] Llave SSH ed25519 → ⏸ pegar en GitHub → `ssh -T git@github.com` → remoto a SSH

## Bloque 4 — Ollama
- [ ] Modelo con tools en ≤ ~4,5 GB de VRAM libres (ref. `qwen3:4b-instruct`)
- [ ] `ollama ps` en GPU; `num_ctx` según OpenClaw

## Bloque 5 — Cerebro: OpenClaw
- [ ] Leer doc (Linux, instalación, onboarding, gateway auth, openai-http-api, Ollama, exec approvals, security)
- [ ] Instalar por el método oficial; fijar el submodule en el tag instalado
- [ ] ⏸ Onboarding (Gemini Flash + Ollama, sin canales, loopback + token, servicio de usuario)
- [ ] Agente `jarvis` + `brain/agent/SOUL.md` mínimo + `scripts/sync-brain.sh`
- [ ] chatCompletions activado; token a `.env` sin imprimirlo
- [ ] Aprobaciones de exec (borrar/instalar/enviar/desplegar)
- [ ] Pruebas: `/v1/models`, "hola" con Gemini y con Ollama, `openclaw security audit` ⏸

## Bloque 6 — Cara en Linux + puente
- [ ] Endurecimiento obligatorio: HUD en 127.0.0.1 con token (HTTP + WS), `/api/providers` sin keys, keys solo desde `.env`, `power_command`/`run_python` con confirmación o desactivados
- [ ] Opción A probada y registrada (D-004)
- [ ] Port de `install.bat`/`start.bat` a `.sh`; quitar/reemplazar lo exclusivo de Windows
- [ ] venv 3.11, dependencias, faster-whisper CUDA, wake word ONNX
- [ ] Proveedor `openclaw` en `face/config.yaml` (sin historial reenviado, timeout, sin fallback silencioso)
- [ ] `jarvis-face.service`, `start-all.sh`, `stop-all.sh`, `doctor.sh`
- [ ] ⏸ Prueba de voz: "Hey Jarvis" → "hola" → respuesta hablada

## Bloque 7 — Voz y personalidad
- [ ] STT con idioma configurable (es por defecto); TTS con `lang_code` configurable
- [ ] ⏸ Muestras de voces Kokoro en `tmp/voces/`
- [ ] SOUL.md completo
- [ ] HUD: escuchando / pensando / hablando / ejecutando + cerebro activo
- [ ] Wake word en español: evaluar y documentar

## Bloque 8 — Cambio de cerebro por voz
- [ ] "usa Gemini / usa el modelo local" → `x-openclaw-model`, persistido y en el HUD
- [ ] Alias para Claude y GPT (⏸ credenciales del usuario)

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
- [ ] Música · [ ] Documento · [ ] Página web · [ ] Horario → calendario · [ ] Pendientes + resumen diario

## Terminado cuando
- [ ] `doctor.sh` en verde; gateway y face arrancan solos; voz: saludo, música, documento, cambio de cerebro, pendientes; docs al día; ⏸ push
