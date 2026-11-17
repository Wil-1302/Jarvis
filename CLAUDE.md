# Proyecto JARVIS — instrucciones para Claude Code

Eres el ingeniero principal de este proyecto. El usuario es el dueño. Habla con él en español y llámalo
"señor" en los resúmenes.

**Fuente de verdad de la migración:** [`docs/MISION_ARCH.md`](docs/MISION_ARCH.md). Si el contexto se compacta
o empieza una sesión nueva, relee ese archivo y [`docs/BITACORA.md`](docs/BITACORA.md) antes de seguir.

## Qué estamos construyendo

Un asistente personal estilo J.A.R.V.I.S. para **Arch Linux nativo** (Hyprland, Wayland), hecho con dos piezas
que corren en la misma máquina como **servicios systemd de usuario**:

1. **La cara (`face/`)**: fork de PanPenek/JarvisAi (Python 3.11). Escucha, habla y se ve:
   wake word "Hey Jarvis" (ONNX de openWakeWord), voz a texto (faster-whisper), texto a voz (Kokoro)
   y un HUD web estilo Iron Man en `http://127.0.0.1:7860` (con token). Servicio: `jarvis-face.service`.
2. **El cerebro (`brain/`)**: OpenClaw (openclaw/openclaw, MIT), instalado desde su paquete oficial.
   Gestiona modelos (Claude Opus 5.5 vía el login de Claude Code como principal y ChatGPT/Codex OAuth como respaldo; D-008), el agente
   `jarvis`, memoria, skills, servidores MCP, aprobaciones de exec y tareas programadas.
   Servicio: el gateway de OpenClaw como servicio de usuario.

**El puente:** la cara no decide nada. Envía lo que dijo el usuario al Gateway de OpenClaw por su endpoint
compatible con OpenAI:

- `POST http://127.0.0.1:18789/v1/chat/completions` (se activa con
  `gateway.http.endpoints.chatCompletions.enabled: true`).
- Auth: `Authorization: Bearer <token del gateway>` (en `.env` como `OPENCLAW_GATEWAY_TOKEN`).
- El agente va en `model` (`openclaw/jarvis`; verificar con `GET /v1/models`).
- `x-openclaw-model: <proveedor/modelo>` cambia el modelo por petición (base del "cambio de cerebro"). Es una
  selección estricta: sin fallback automático.
- Un `user` estable hace que las peticiones compartan sesión: el historial vive en OpenClaw.

**Reparto de acciones (opción A, ver DECISIONES.md):** OpenClaw ejecuta todas las acciones (shell con
aprobaciones + MCP). face queda como voz + HUD; sus tools locales se apagan en modo OpenClaw
(salvo, quizá, medios y volumen por latencia).

```
[Micrófono] → face (wake word → STT) ── HTTP 127.0.0.1 ──> OpenClaw Gateway → modelo + skills + MCP
[Parlantes] ← face (TTS + HUD)       <────────────────── respuesta ───────────┘
```

## Principio clave: fusionar sin mezclar código

- `face/` es NUESTRO código: se modifica libremente. Se importó con `git subtree` para poder traer cambios
  del original.
- `brain/openclaw/` es un **git submodule de solo lectura** (para consultar código y docs), fijado en el tag
  de la versión instalada. **No se edita el código de OpenClaw.** Se personaliza SOLO con: configuración,
  el agente `jarvis` (`brain/agent/`), skills propias (`skills/`) y servidores MCP (`mcp/`).
  `scripts/sync-brain.sh` copia todo eso hacia `~/.openclaw`. Motivo: OpenClaw recibe parches de seguridad
  frecuentes y debemos poder actualizarlo sin conflictos.

## Estructura

```
~/Proyectos/Jarvis/
├── CLAUDE.md
├── README.md
├── .env.example          # nombres de variables, NUNCA secretos reales (.env real: permisos 600)
├── face/                 # fork de PanPenek/JarvisAi (git subtree)
├── brain/
│   ├── openclaw/         # submodule de openclaw/openclaw (solo lectura)
│   ├── agent/            # SOUL.md, AGENTS.md del agente "jarvis"
│   └── config/           # plantilla de config de OpenClaw (sin tokens)
├── skills/               # NUESTRAS skills (SKILL.md); se sincronizan hacia OpenClaw
├── mcp/                  # config de cada servidor MCP + mcp/<nombre>.md
├── scripts/
│   ├── arch/             # scripts que requieren root (los ejecuta el usuario)
│   ├── sync-brain.sh, start-all.sh, stop-all.sh, doctor.sh
│   └── systemd/          # unidades de usuario (jarvis-face.service)
└── docs/                 # MISION_ARCH, BITACORA, PLAN, DECISIONES, ENTORNO_ARCH, ANALISIS_FACE
```

## Modo de trabajo

- Autónomo, bloque por bloque y en orden (ver `docs/PLAN.md`). No preguntar lo que se puede averiguar.
- `docs/BITACORA.md`: fecha, bloque, qué se hizo, qué falta, problemas.
- Al cerrar cada bloque: commits pequeños en español, actualizar `docs/PLAN.md` y seguir.
- Si algo falla dos veces con enfoques distintos: anotarlo, pasar a un bloque independiente y avisar al final.
- **Solo se detiene (⏸)** para: sudo, escribir keys/tokens o iniciar sesión, descargas de >2 GB, acciones
  destructivas/irreversibles/de pago, instalar un MCP o algo con control nuevo sobre el sistema, `git push`,
  y decisiones de arquitectura no resueltas. En cada parada: comando exacto y qué debe ver el usuario.

## Reglas de seguridad (obligatorias)

- Nunca `pacman -Sy` solo: siempre `pacman -Syu --needed`.
- Nunca `sudo npm` ni `sudo pip`. npm global con prefijo en `~/.local`.
- Nunca `curl | bash` sin descargar, leer y resumir el script al usuario.
- AUR: resumir el PKGBUILD (qué descarga, de dónde, qué ejecuta) y pedir OK.
- Nada de skills de ClawHub o de terceros sin revisión y aprobación del usuario.
- Secretos solo en `.env` (permisos 600) o en la config de OpenClaw. Nunca en el repo, en `config.yaml`,
  en pantalla ni en mensajes (como mucho: "existe, N caracteres").
- Gateway, HUD y MCP con HTTP: solo en `127.0.0.1`. El token del gateway equivale a acceso de operador.
- Pedir confirmación antes de borrar, instalar, enviar o desplegar (en OpenClaw: aprobaciones de exec;
  en skills: confirmación por voz).
- Si la documentación actual de OpenClaw o de un repo contradice este archivo, gana la documentación:
  verificar y actualizar este archivo.

## Entorno (ver `docs/ENTORNO_ARCH.md`)

- Arch Linux, Hyprland/Wayland, RTX 4050 Laptop 6 GB (MUX en modo dGPU; ~1,6 GB de VRAM los usa el escritorio),
  24 GB de RAM, PipeWire.
- Python 3.11 para face (venv en `face/.venv`, gestionado con uv). Node 26 (sistema) para OpenClaw.
- Sin Ollama ni CUDA de sistema (D-008). OpenClaw 2026.11.5 por npm en `~/.local`; gateway `openclaw-gateway.service`
  con el encierro `scripts/systemd/openclaw-gateway.service.d/`.
- Herramientas de escritorio en Wayland: `wpctl`, `playerctl`, `brightnessctl`, `notify-send`, `wl-clipboard`,
  `ydotool` (servicio de usuario).

## Convenciones

- Commits pequeños y descriptivos en español, uno por paso lógico.
- Los scripts de `scripts/` son idempotentes y muestran qué hacen antes de hacerlo. `doctor.sh` es solo lectura.
- `docs/PLAN.md` al día con `[x]` lo hecho y `[ ]` lo pendiente.

## Notas sobre el repo original de face

- URL correcta: https://github.com/PanPenek/JarvisAi (su README menciona otra URL de clonado; ignorarla).
- El README dice MIT pero el repo no incluye archivo LICENSE (ver DECISIONES.md D-003).
- Hallazgos de seguridad y puntos de integración: `docs/ANALISIS_FACE.md` (siguen vigentes).

## Repo

- Remoto: `github.com/Wil-1302/Jarvis` (**público**). Push solo cuando el usuario lo pida; nunca force push.
- Tag `jarvis-wil-v1` = versión anterior (JARVIS-WIL).
