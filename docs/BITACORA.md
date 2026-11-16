# Bitácora

Formato: fecha · bloque · qué se hizo · qué falta · problemas.

## 2026-11-16 · Inicio
- Repo clonado en `~/Proyectos/Jarvis` (HTTPS) y submodule `brain/openclaw` inicializado (depth 1, `1d72ad0`).
- Misión guardada en `docs/MISION_ARCH.md` (fuente de verdad).

## 2026-11-16 · Bloque 0 — Auditoría ✅
- Hecho: `docs/ENTORNO_ARCH.md`.
- Hallazgos clave: MUX en modo dGPU (no híbrido); la NVIDIA ya usa ~1,6 GB de VRAM por el escritorio;
  solo 25 GB libres en disco; Node 26 ya instalado (recomendado por OpenClaw); `ollama-cuda` arrastra
  `cuda` (2,43 GiB) → requiere OK; Spotify de escritorio ya instalado; sin `~/.ssh` ni `~/.gitconfig`.

## 2026-11-16 · Bloque 1 — Documentación a Arch ✅
- Hecho: CLAUDE.md reescrito (Arch, systemd de usuario, opción A, reglas de la misión); DECISIONES D-005 (migración)
  y D-006 (Node 26 del sistema, recomendado por OpenClaw); plan B de Windows marcado obsoleto; PLAN.md por bloques;
  README, .env.example y READMEs de scripts/ y brain/agent/ sin WSL/PowerShell.
