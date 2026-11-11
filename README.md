# JARVIS

Asistente personal estilo J.A.R.V.I.S. para Windows, formado por dos piezas:

- **`face/`**: la cara. Escucha, habla y se ve: wake word "Hey Jarvis", STT (faster-whisper), TTS (Kokoro)
  y un HUD web en http://localhost:7860. Corre en Windows nativo. Es un fork de
  [PanPenek/JarvisAi](https://github.com/PanPenek/JarvisAi) importado con `git subtree` (ver `face/CREDITS.md`).
- **`brain/`**: el cerebro. [OpenClaw](https://github.com/openclaw/openclaw) corre en WSL2 y gestiona los modelos,
  los agentes, la memoria, las skills, los servidores MCP y las tareas programadas. `brain/openclaw/` es un submodule
  de solo lectura; nuestra personalización vive en `brain/agent/`, `brain/config/`, `skills/` y `mcp/`.

```
[Micrófono] → face (wake word → STT) ── HTTP ──> OpenClaw Gateway (WSL2) → modelo + skills + MCP
[Parlantes] ← face (TTS + HUD)       <──────────────── respuesta ───────────────┘
```

## Estructura

| Ruta | Contenido |
|---|---|
| `face/` | Código de la cara (nuestro; se modifica libremente) |
| `brain/openclaw/` | Submodule de OpenClaw, **solo lectura** |
| `brain/agent/` | SOUL.md / AGENTS.md del agente `jarvis` |
| `brain/config/` | Plantilla de configuración de OpenClaw (sin tokens) |
| `skills/` | Skills propias (SKILL.md) que se sincronizan hacia OpenClaw |
| `mcp/` | Configuración y notas de instalación de cada servidor MCP |
| `scripts/` | setup / start-all / stop-all / doctor / sync-brain (PowerShell) |
| `docs/` | PLAN, ARQUITECTURA, ANALISIS_FACE, DECISIONES |

## Clonar

```powershell
git clone --recurse-submodules git@github.com:Wil-1302/Jarvis.git
# o, si ya está clonado:
git submodule update --init --depth 1
```

La versión anterior del proyecto (JARVIS-WIL) se conserva en el tag `jarvis-wil-v1`.

Estado y hoja de ruta: [docs/PLAN.md](docs/PLAN.md).
