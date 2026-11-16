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
