# MISIÓN

> Fuente de verdad de la migración a Arch Linux. Si el contexto se compacta o
> empieza una sesión nueva: releer este archivo y docs/BITACORA.md antes de seguir.

# Contexto
- Migré de Windows a Arch Linux nativo en el mismo PC (WSL estaba
  corrupto). Todo lo de Windows/WSL del repo queda obsoleto.
- Lee CLAUDE.md, docs/PLAN.md, docs/DECISIONES.md y docs/ANALISIS_FACE.md.
  Siguen vigentes: la arquitectura, las reglas de seguridad y los hallazgos
  del análisis de face.
- Hardware (verifícalo): 24 GB de RAM, NVIDIA RTX 4050 de 6 GB, portátil
  (probablemente gráficos híbridos).
- Arquitectura: face/ (fork de PanPenek/JarvisAi: voz + HUD, Python) habla
  con OpenClaw (cerebro: modelos, skills, MCP) por su endpoint compatible
  con OpenAI en http://127.0.0.1:18789/v1. brain/openclaw es un submodule
  de solo lectura: OpenClaw se instala desde su paquete oficial y se
  personaliza solo con config, agente, skills y MCP.

# ⚠️ CAMBIO DE PLANES (2026-11-17) — prevalece sobre los bloques de abajo (D-008)
- **Sin Ollama y sin API keys.** Cerebro principal: **Claude** reutilizando el login local de Claude Code
  (runtime `claude-cli` de OpenClaw), con el mejor modelo que permita el plan (Pro → Opus 5.5; Fable pide
  créditos extra). Respaldo automático: **ChatGPT con OAuth de Codex**
  (`openclaw models auth login --provider openai`, modelo `openai/gpt-6-astra`). **Gemini queda fuera.**
- Prioridad: resultados ya; menos paradas y más construir.
- Orden nuevo:
  1. Quitar Ollama/CUDA (face no necesita /opt/cuda: faster-whisper trae sus libs CUDA por pip).
  2. OpenClaw con aislamiento (capas 1 y 2 + refuerzos a-e, ver docs/AISLAMIENTO_OPENCLAW.md); el gateway debe
     poder usar ~/.claude; las rutas de credenciales nunca en la lista de ejecución libre.
  3. ⏸ Onboarding: reutilizar el login de Claude (hecho sin interacción) y login de ChatGPT (lo hace el usuario). Sin canales.
  4. primary = Claude, fallbacks = Codex; probar el failover. Si OpenClaw no salta solo al agotar límites,
     face reintenta con `x-openclaw-model` hacia GPT y avisa por voz: "Señor, cambio al cerebro de respaldo".
  5. Gateway con curl; luego face: seguridad mínima, port a Linux, puente, Whisper en GPU (o CPU), Kokoro en CPU.
     ⏸ Prueba de voz.
  6. Primeras habilidades sin cuentas externas: "abre [aplicación]" y "escríbeme una receta en un documento"
     (.docx abierto en LibreOffice), con prueba de voz.
  7. Después, Bloque 7 y los MCP.
- **Paradas solo para:** sudo, logins del usuario y pruebas de voz. Lo demás se decide y se anota en la bitácora.
- Bloques 4 (Ollama) y 8 (cambio de cerebro Gemini/local) quedan **obsoletos** en lo que contradigan esto.

# Modo de trabajo
- Trabaja de forma autónoma, bloque por bloque y en orden. No me preguntes
  lo que puedas averiguar tú.
- Lleva docs/BITACORA.md: fecha, bloque, qué hiciste, qué falta, problemas.
- Al cerrar cada bloque: commits pequeños en español, actualiza
  docs/PLAN.md y sigue.
- Si algo falla dos veces con enfoques distintos: anótalo en la bitácora,
  pasa a un bloque independiente y avísame al final.
- SOLO te detienes (⏸) para: 1) sudo (no tienes mi contraseña; agrupa lo de
  root en scripts que ejecuto yo), 2) escribir keys, tokens o iniciar
  sesión (lo hago yo), 3) descargas de más de 2 GB, 4) acciones
  destructivas, irreversibles o que cuesten dinero, 5) instalar un MCP o
  algo que dé control nuevo sobre el sistema, 6) git push, 7) decisiones
  de arquitectura que esta misión no resuelva. En cada parada dime el
  comando exacto y qué debo ver.

# Reglas de seguridad
- Nunca pacman -Sy solo: siempre pacman -Syu --needed.
- Nunca sudo npm ni sudo pip. npm global con prefijo en ~/.local.
- Nunca curl | bash sin descargar, leer y resumirme el script.
- AUR: resume el PKGBUILD (qué descarga, de dónde, qué ejecuta) y pide OK.
- Nada de skills de ClawHub o de terceros sin revisión y aprobación.
- Secretos solo en .env (permisos 600) o en la config de OpenClaw. Nunca en
  el repo, en config.yaml, en pantalla ni en tus mensajes (como mucho,
  "existe, N caracteres").
- Gateway, HUD y MCP con HTTP: solo en 127.0.0.1.
- El repo es público. Sin force push; push solo con mi OK.

# Bloque 0 — Auditoría (solo lectura)
Distro, escritorio, sesión ($XDG_SESSION_TYPE), GPU (lspci, nvidia-smi,
híbrida o no), RAM, disco, audio (wpctl status, micrófonos), herramientas
instaladas (git, ssh, python, uv, node, ollama, docker, yay/paru), llave
SSH y git config. Escribe docs/ENTORNO_ARCH.md con lo que hay y lo que
falta.

# Bloque 1 — Documentación a Arch
- Reescribe CLAUDE.md para Arch: mismo propósito, arquitectura, principio
  "fusionar sin mezclar código" y reglas; sin Windows/WSL; rutas en
  ~/Proyectos/Jarvis; OpenClaw y face nativos con servicios systemd de
  usuario. Enlaza docs/MISION_ARCH.md.
- DECISIONES.md: nueva decisión "Migración a Arch Linux nativo"; marca el
  Plan B de Windows como obsoleto sin borrarlo.
- PLAN.md replanificado según estos bloques. Commit.

# Bloque 2 — Paquetes del sistema (⏸ sudo, una sola vez)
Crea scripts/arch/01-sistema.sh: idempotente, explica qué hará y pide
confirmación. Verifica los nombres en los repos actuales. Incluye:
- base-devel git openssh jq ripgrep ffmpeg xdg-utils uv
- Node 24 LTS (paquete LTS de Arch, o mise/fnm a nivel usuario si es más
  limpio; decide y documenta)
- Ollama con CUDA y su servicio habilitado (que use la NVIDIA si es híbrida)
- portaudio, espeak-ng (Kokoro lo necesita para español)
- wl-clipboard playerctl libnotify brightnessctl at-spi2-core, ydotool con
  permisos de /dev/uinput
- libreoffice-fresh y su paquete de español
- loginctl enable-linger para mi usuario
- Opcional, pregúntame: ufw negando todo lo entrante
Detente y dame el comando: sudo bash scripts/arch/01-sistema.sh

# Bloque 3 — Entorno de usuario
uv python install 3.11. Prefijo npm en ~/.local y ~/.local/bin en el PATH
de mi shell. Si no hay llave SSH: créala (ed25519), ⏸ dime dónde pegarla
en GitHub, prueba ssh -T git@github.com y pasa el remoto a SSH.

# Bloque 4 — Ollama
Modelo con soporte de tools que quepa en 6 GB de VRAM (referencia
qwen3:4b-instruct; ⏸ si pasa de 2 GB). Verifica con ollama ps que corre en
GPU. Ajusta num_ctx según lo que pida la doc de OpenClaw, sin truncar el
prompt ni salirse de la GPU. Es el cerebro local; el principal será
Gemini Flash. No pierdas tiempo afinando el 4B.

# Bloque 5 — Cerebro: OpenClaw
- Lee la doc del submodule (Linux, instalación, onboarding, gateway auth,
  openai-http-api, Ollama, aprobaciones de exec, security). Instala con el
  método oficial y fija el submodule en el tag instalado.
- ⏸ Onboarding lo hago yo: dame el comando y qué elegir en cada pantalla.
  Gemini (key de AI Studio, modelo Flash) + Ollama en 127.0.0.1:11434,
  ningún canal, gateway en loopback con token, servicio systemd de usuario.
- Agente "jarvis" con brain/agent/SOUL.md mínimo (español, breve, formal,
  me llama "señor") y scripts/sync-brain.sh idempotente.
- Gateway: 127.0.0.1, token y chatCompletions activado. Copia el token a
  .env (OPENCLAW_GATEWAY_TOKEN) sin imprimirlo.
- Aprobaciones de exec: borrar, instalar, enviar o desplegar pide
  confirmación.
- Pruebas: GET /v1/models; "hola" al agente jarvis con Gemini y otra vez
  con x-openclaw-model apuntando a Ollama; openclaw security audit.
  ⏸ Muéstrame los resultados.

# Bloque 6 — Cara en Linux + puente
1. Primero lo obligatorio de PLAN.md Fase 3: HUD en 127.0.0.1 con token
   (HTTP y WebSocket), /api/providers sin keys, keys solo desde .env,
   power_command y run_python con confirmación o desactivados.
2. Tools: como todo está en la misma máquina, prefiero la opción A:
   OpenClaw ejecuta todas las acciones (shell + MCP) y face queda como voz
   + HUD, con sus tools locales apagadas en modo OpenClaw (salvo quizá
   medios y volumen por latencia). Compruébalo con una prueba real y
   registra la decisión.
3. Port: install.bat/start.bat → scripts .sh; lo exclusivo de Windows se
   elimina o se reemplaza (wpctl, brightnessctl, notify-send, playerctl,
   wl-clipboard) solo si el punto 2 lo mantiene.
4. venv Python 3.11, dependencias, faster-whisper con CUDA (si se complica,
   CPU y anota la tarea), wake word con los ONNX de openWakeWord.
5. Proveedor openclaw en face/config.yaml: base_url, agente jarvis, token
   desde .env, user estable, timeout y sin fallback silencioso. No
   reenviar historial si OpenClaw mantiene la sesión (ANALISIS_FACE §6).
6. Servicio systemd jarvis-face.service y scripts start-all.sh,
   stop-all.sh y doctor.sh (solo lectura).
7. ⏸ Prueba conmigo: "Hey Jarvis" (pronunciado en inglés) → "hola" →
   responde con voz.

# Bloque 7 — Voz y personalidad
- STT con idioma configurable (español por defecto); TTS con lang_code
  configurable.
- ⏸ Genera muestras en tmp/voces/ de varias voces de Kokoro (bm_* para el
  estilo Jarvis; em_*/ef_* para español) con la misma frase. Yo elijo.
- SOUL.md completo: formal, breve, ingenio seco, confirma antes de acciones
  importantes y termina con "¿Algo más, señor?".
- HUD: estados escuchando/pensando/hablando/ejecutando y cerebro activo.
- Wake word en español: evalúa modelo propio de openWakeWord, otra palabra
  o push-to-talk con tecla global. Recomienda y documenta.

# Bloque 8 — Cambio de cerebro por voz
"Jarvis, usa Gemini / usa el modelo local" → x-openclaw-model, persistido y
visible en el HUD. Deja alias listos para Claude (API key de Anthropic) y
GPT (login de ChatGPT o API key); ⏸ esas credenciales las agrego yo.

# Bloque 9 — MCP, uno por uno (⏸ OK antes de cada uno)
Para cada uno: lee README y código por encima, fija versión, config en
mcp/, conéctalo a OpenClaw, prueba real y documenta en mcp/<nombre>.md.
1. Escritorio: agent-sh/computer-use-linux (ejecuta su doctor; deja
   run_shell desactivado).
2. Spotify: cliente de escritorio (AUR o Flatpak, pregúntame) +
   marcelmarais/spotify-mcp-server para buscar. Controlar reproducción por
   API requiere Premium: prueba reproducir la URI por MPRIS
   (playerctl open spotify:track:...), que podría funcionar sin Premium.
   Meta: "pon X de Y" → busca → abre Spotify → suena.
3. Documentos: GongRzhe/Office-Word-MCP-Server + LibreOffice para abrir.
   Meta: "escríbeme una receta en un documento" → se crea y se abre.
4. Google Calendar: nspady/google-calendar-mcp (⏸ guíame con el cliente
   OAuth de Google Cloud). Debe importar horarios de imagen/PDF y manejar
   eventos recurrentes.
5. GitHub: MCP oficial (token fine-grained mínimo, ⏸).
6. Render: MCP oficial (API key, ⏸).
7. AWS: awslabs/mcp o su sucesor (mínimo privilegio, ⏸). Puede ir al final.
8. Packet Tracer: versión Linux (⏸ se descarga de Cisco NetAcad) +
   Mats2208/MCP-Packet-Tracer (soporte Linux no probado: pruébalo).

# Bloque 10 — Skills propias (skills/, sincronizadas con sync-brain.sh)
1. Música: "reproduce [canción] de [artista]".
2. Documento: "abre un documento y hazme [contenido]".
3. Página web: requisitos (preguntados o deducidos) → construir → abrir en
   el navegador → "Señor, ¿está bien o cambiamos algo?" → al aprobar,
   preguntar destino (GitHub Pages / Render / AWS) → desplegar con
   confirmación.
4. Horario → calendario: leer imagen/PDF → proponer eventos → preguntar si
   se repite (solo esta semana / N semanas / indefinido) → crear con
   confirmación.
5. Pendientes: "¿qué tengo pendiente hoy?" + resumen diario programado.

# Terminado cuando
doctor.sh todo en verde; gateway y face arrancan solos al iniciar sesión;
por voz funcionan saludo, música, documento, cambio de cerebro y
pendientes; docs al día; push hecho con mi OK.
