# Proyecto JARVIS — instrucciones para Claude Code

Eres el ingeniero principal de este proyecto. El usuario es el dueño. Habla con él en español.

## Qué estamos construyendo

Un asistente personal estilo J.A.R.V.I.S. para Windows, hecho con dos piezas:

1. **La cara (`face/`)**: fork de PanPenek/JarvisAi (Python). Es lo que escucha, habla y se ve:
   palabra de activación "Hey Jarvis" (openWakeWord), voz a texto (faster-whisper), texto a voz (Kokoro),
   y un HUD web estilo Iron Man en http://localhost:7860. Corre en **Windows nativo**
   (necesita micrófono, parlantes y acceso al escritorio).
2. **El cerebro (`brain/`)**: OpenClaw (openclaw/openclaw, MIT). Gestiona modelos (Claude, GPT, Gemini, Ollama),
   agentes, memoria, skills, servidores MCP y tareas programadas. Corre en **WSL2**, que es la ruta
   recomendada por OpenClaw en Windows.

**El puente:** la cara no decide nada por sí sola. Envía lo que dijo el usuario al Gateway de OpenClaw
por su endpoint compatible con OpenAI:

- `POST http://127.0.0.1:18789/v1/chat/completions` (desactivado por defecto).
- Se activa con `gateway.http.endpoints.chatCompletions.enabled: true`.
- Auth: `Authorization: Bearer <token del gateway>`.
- El agente se elige en el campo `model` (`openclaw:<agentId>` u `openclaw/<agentId>` según la versión;
  verifícalo con `GET /v1/models`).
- El header `x-openclaw-model` permite cambiar el modelo por petición (base del "cambio de cerebro").
- Si se envía un `user` estable, las peticiones comparten sesión.

La cara ya soporta proveedores tipo `openai` con `base_url` en `config.yaml`, así que OpenClaw entra
como un proveedor más.

```
[Micrófono] → face (wake word → STT) ── HTTP ──> OpenClaw Gateway (WSL2) → modelo + skills + MCP
[Parlantes] ← face (TTS + HUD)       <──────────────── respuesta ───────────────┘
```

## Principio clave: fusionar sin mezclar código

- `face/` es NUESTRO código: se modifica libremente. Se importa con `git subtree` para poder traer
  cambios del original si los hay.
- `brain/openclaw/` es un **git submodule de solo lectura** (para consultar código y docs).
  **No se edita el código de OpenClaw.** OpenClaw se instala desde su paquete oficial dentro de WSL2
  y se personaliza SOLO con: configuración, el agente Jarvis (SOUL.md / AGENTS.md), skills propias
  y servidores MCP. Motivo: OpenClaw recibe parches de seguridad frecuentes y tenemos que poder
  actualizarlo sin conflictos.

## Estructura objetivo

```
jarvis/
├── CLAUDE.md
├── README.md
├── .gitignore
├── .env.example          # plantillas de variables, NUNCA secretos reales
├── face/                 # fork de PanPenek/JarvisAi (git subtree)
├── brain/
│   ├── openclaw/         # submodule de openclaw/openclaw (solo lectura)
│   ├── agent/            # SOUL.md, AGENTS.md del agente "jarvis"
│   └── config/           # plantilla de config de OpenClaw (sin tokens)
├── skills/               # NUESTRAS skills (SKILL.md); se sincronizan hacia OpenClaw
├── mcp/                  # config de cada servidor MCP + notas de instalación
├── scripts/              # setup.ps1, start-all.ps1, stop-all.ps1, doctor.ps1, sync-brain.ps1
└── docs/                 # PLAN.md, ARQUITECTURA.md, ANALISIS_FACE.md, DECISIONES.md
```

## Hoja de ruta

Trabaja **una fase a la vez**. Al terminar cada fase, detente, resume qué hiciste y explica cómo probarlo.
No avances a la siguiente fase sin que el usuario lo apruebe.

- **Fase 1 — Montaje.** Verificar requisitos; crear el monorepo; subtree de face; submodule de openclaw;
  analizar el código de face; escribir docs/ANALISIS_FACE.md y docs/PLAN.md.
- **Fase 2 — Cerebro.** Instalar Node 24 y OpenClaw en WSL2; onboarding; crear el agente `jarvis`;
  activar el endpoint chatCompletions con auth por token, escuchando solo en loopback. Probar con curl
  desde PowerShell (Windows → WSL2). Si localhost no llega a WSL2, documentar la solución
  (por ejemplo, el modo de red "mirrored" de WSL).
- **Fase 3 — Puente.** Añadir el proveedor `openclaw` en face/config.yaml (base_url
  `http://127.0.0.1:18789/v1`, token leído desde `.env`, `user` estable para conservar sesión).
  Decidir y documentar qué pasa con las 31 tools locales de face:
  (A) desactivarlas en modo OpenClaw y que OpenClaw haga todo (escritorio vía Windows-MCP por HTTP), o
  (B) enviarlas como function tools (la doc de OpenClaw indica que el endpoint acepta un subconjunto de
  tools tipo función) para que el control del escritorio se ejecute en Windows nativo.
  Probar ambas, recomendar una y registrar la decisión en docs/DECISIONES.md.
- **Fase 4 — Personalidad y voz.** STT en español; elegir voz TTS (listar las voces de Kokoro instaladas:
  masculinas británicas para inglés y voces en español); persona Jarvis: formal, breve, ingenioso,
  llama al usuario "señor". Mostrar estados (escuchando / pensando / hablando) en el HUD.
- **Fase 5 — Cambio de cerebro.** Comando de voz "Jarvis, usa Claude / GPT / Gemini / modo local"
  → face envía `x-openclaw-model` o cambia el modelo del agente. Mostrar el cerebro activo en el HUD.
- **Fase 6 — Cuerpo (MCP), uno por uno, cada uno con su prueba:**
  Windows-MCP (CursorTouch), Spotify (requiere Spotify Premium para controlar la reproducción),
  Office-Word-MCP-Server (GongRzhe), Google Calendar (nspady/google-calendar-mcp),
  GitHub MCP oficial, Render MCP oficial, AWS (awslabs/mcp o su sucesor), Packet Tracer (Mats2208).
- **Fase 7 — Skills propias.**
  (a) Flujo web: pedir requisitos o deducirlos → construir → abrir en el navegador →
  "Señor, ¿está bien o cambiamos algo?" → al aprobar, preguntar destino (GitHub / Render / AWS) y desplegar.
  (b) Horario → calendario: leer imagen o PDF, proponer los eventos, preguntar si se repiten
  (solo esta semana / N semanas / indefinido) y crearlos tras confirmación.

## Reglas de seguridad (obligatorias)

- Nunca commitear secretos. Tokens y API keys solo en `.env` (incluido en .gitignore).
  Mantener `.env.example` con los nombres de variables y valores vacíos.
- El Gateway de OpenClaw escucha solo en 127.0.0.1. Su token equivale a acceso total de operador:
  tratarlo como una contraseña.
- NO instalar skills de ClawHub ni de terceros sin que el usuario lea y apruebe el código.
  Preferir skills propias en `skills/`.
- Pedir confirmación antes de: comandos con administrador, borrar archivos, instalar software del sistema,
  desplegar, enviar correos o mensajes, o cualquier cosa que cueste dinero.
- Las skills con acciones destructivas o irreversibles deben pedir confirmación por voz.
- Si la documentación actual de OpenClaw o de algún repo contradice este archivo, gana la documentación:
  verifícalo y actualiza este archivo.

## Entorno

- Windows 10/11. Claude Code corre en Windows nativo desde la carpeta del repo.
  Para ejecutar en WSL: `wsl -e bash -lc "<comando>"`.
- Python 3.11 para face (venv en `face/.venv`). Node 24 dentro de WSL2 para OpenClaw.
- La carpeta del repo NO debe estar dentro de OneDrive (evitar Escritorio/Documentos sincronizados).

## Convenciones

- Commits pequeños y descriptivos en español, uno por paso lógico.
- Los scripts de `scripts/` deben ser idempotentes y mostrar qué hacen antes de hacerlo.
- Mantener docs/PLAN.md al día con [x] lo hecho y [ ] lo pendiente.

## Notas sobre el repo original de face

- URL correcta: https://github.com/PanPenek/JarvisAi (su README menciona otra URL de clonado; ignorarla).
- Es un proyecto pequeño (pocos commits). El README dice MIT pero el repo no incluye archivo LICENSE:
  anotarlo en docs/DECISIONES.md.

## Repo

- Remoto: `git@github.com:Wil-1302/Jarvis.git` (**público**). Push solo cuando el usuario lo pida; nunca force push.
- Tag `jarvis-wil-v1` = versión anterior (JARVIS-WIL: pipeline de voz local propio, commits c9e76a6 y 3f8d29c).
- Smart App Control (activo en este PC) bloqueó `_liblinear.pyd` de sklearn, del que depende el paquete
  `openwakeword`. En JARVIS-WIL se resolvió ejecutando los modelos ONNX de openWakeWord directamente con
  onnxruntime. Revisar esto al instalar las dependencias de face.
