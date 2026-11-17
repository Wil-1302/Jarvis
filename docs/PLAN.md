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

## Bloque 2 — Paquetes del sistema
- [x] `scripts/arch/01-sistema.sh` (idempotente, con confirmación; + pacman-contrib)
- [x] Ejecutado 2026-11-17: sistema actualizado, Ollama **CUDA** en 127.0.0.1, uinput (linger lo activó Claude después)
- [ ] ⏸ ufw: no se instaló (se respondió "no") → volver a ejecutar el script eligiendo 1 y "s"
- [ ] ⏸ Decidir: mantener CUDA (5,4 GB) o pasar a Vulkan

## Bloque 3 — Entorno de usuario
- [x] `uv python install 3.11` (3.11.18)
- [x] Prefijo npm en `~/.local` (PATH ya lo tenía en bash y fish)
- [x] git config global
- [x] Llave SSH ed25519 generada
- [ ] ⏸ La llave en GitHub no es esta (huella distinta) → pegar `~/.ssh/id_ed25519.pub` → `ssh -T` → remoto a SSH

## Bloque 4 — Ollama
- [x] GPU detectada por Ollama (CUDA, 4,1 GiB libres)
- [ ] ⏸ Descarga de `qwen3:4b-instruct` (2,5 GB > 2 GB). Alternativa sin parada: `qwen2.5:3b` (1,9 GB)
- [ ] Modelo con tools en ≤ ~4,5 GB de VRAM libres (ref. `qwen3:4b-instruct`)
- [ ] `ollama ps` en GPU; `num_ctx` según OpenClaw

## Bloque 5 — Cerebro: OpenClaw
- [ ] Leer doc (Linux, instalación, onboarding, gateway auth, openai-http-api, Ollama, exec approvals, security)
- [ ] Instalar por el método oficial; fijar el submodule en el tag instalado
- [ ] ⏸ Onboarding (Gemini Flash + Ollama, sin canales, loopback + token, servicio de usuario)
- [ ] Agente `jarvis` + `brain/agent/SOUL.md` mínimo + `scripts/sync-brain.sh`
- [ ] chatCompletions activado; token a `.env` sin imprimirlo
- [ ] Aprobaciones de exec (borrar/instalar/enviar/desplegar)
- [x] Análisis de aislamiento de rutas sensibles: `docs/AISLAMIENTO_OPENCLAW.md` (OpenClaw no confina `exec` por rutas)
- [x] Plantilla del encierro systemd `scripts/systemd/openclaw-gateway.service.d/jarvis-aislamiento.conf` (probada)
- [ ] Capa 1: workspace propio, `tools.fs.workspaceOnly`, modo `guarded`, elevated off, allowlist sin intérpretes/systemd-run/busctl/ydotool
- [ ] Capa 2: `sync-brain.sh` instala el drop-in; verificar con `systemctl --user show openclaw-gateway -p InaccessiblePaths`
- [ ] ⏸ D-007: opción A (recomendada), B (Podman) o C (usuario separado)
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
