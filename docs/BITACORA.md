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

## 2026-11-16 · Bloque 2 — Paquetes del sistema (⏸ esperando sudo)
- Hecho: `scripts/arch/01-sistema.sh` (idempotente, confirma; pregunta backend CUDA/Vulkan y ufw).
  Inspeccionado el paquete `ollama` 0.40.16: servicio de sistema como usuario `ollama`, modelos en `/var/lib/ollama`,
  escucha por defecto en 127.0.0.1 (se fija igualmente por drop-in).
- Decisión: `/dev/uinput` ya tiene ACL de sesión (uaccess) → no se añade el usuario a `input` (evita acceso a todos los
  dispositivos de entrada); solo se asegura la carga de `uinput` al arrancar.
- Falta: que el usuario lo ejecute y elija CUDA (descarga >2 GB) o Vulkan, y ufw sí/no.
- 2026-11-16 (cont.): el script **no llegó a ejecutarse** (pacman.log sin actividad desde 2026-11-15 23:37; sin ollama,
  ufw, drop-in ni linger). En paralelo hay un `yay -S objection` compilando `frida-v8` (V8, `ninja -j 1`, >1 h 40 min)
  lanzado por `~/CyberLab/Scripts/install_02_aur.sh`: ocupa ~14 GB en `~/.cache/yay` y bajó el disco libre de 25 a 16 GB.
  Hay que esperar a que termine antes de ejecutar 01-sistema.sh (bloqueo de la base de pacman).
- Añadido `pacman-contrib` (paccache) al script.

## 2026-11-16 · Bloque 3 — Entorno de usuario (⏸ llave en GitHub)
- Hecho: Python 3.11.18 con uv; `npm config set prefix ~/.local`; `~/.local/bin` ya estaba en el PATH de bash y fish
  (la terminal del usuario es fish); git global (`user.name`, `user.email`, `init.defaultBranch main`, `pull.ff only`);
  llave `~/.ssh/id_ed25519` (ed25519, sin passphrase; se puede añadir con `ssh-keygen -p`); huella de github.com
  verificada contra la oficial y añadida a `known_hosts`.
- Falta: el usuario pega la llave pública en GitHub → `ssh -T git@github.com` → remoto a SSH.

## 2026-11-17 · Verificación del Bloque 2 y SSH
- `01-sistema.sh` sí se ejecutó (16:35–16:45): `pacman -Syu` completo, `pacman-contrib`, `ollama` + **`ollama-cuda` +
  `cuda` 13.5** (se eligió la opción 1, no Vulkan), drop-in de Ollama (escucha solo en 127.0.0.1:11434, GPU detectada
  con 4,1 GiB libres), uinput cargado. **ufw no se instaló** (en el pacman no aparece: se respondió "no").
  **linger quedó en `no`** (el script se cortó en el paso 4, sin mensaje en el journal); Claude lo activó con
  `loginctl enable-linger wil` (polkit lo permite sin sudo) → `Linger=yes`.
- Disco: 24 GB libres; `~/.cache/yay` aún ocupa 7,6 GB; `/opt/cuda` 5,4 GB.
- SSH: `Permission denied (publickey)`. La única llave en GitHub (`SHA256:2gfWxS6Q…`) no es la de esta máquina
  (`SHA256:LKd1PL0x…`, comentario `wil@archwil-jarvis`). El remoto sigue en HTTPS.
- Bloque 4: `qwen3:4b-instruct` pesa 2,5 GB → parada por la regla de >2 GB.

## 2026-11-17 · Bloque 5 (adelanto) — Aislamiento de rutas sensibles
- Leída la doc de sandbox, permission modes, tool policy, exec approvals y fs-safe. OpenClaw confina
  `read`/`write`/`edit`/`apply_patch` al workspace, pero no `exec` por rutas.
- Probado `InaccessiblePaths` en unidades de usuario (systemd 262): bloquea `~/.ssh`, `~/CyberLab`, navegadores, etc.;
  playerctl/notify-send siguen funcionando. Evasión confirmada vía `systemd-run --user`.
- Hecho: `docs/AISLAMIENTO_OPENCLAW.md`, plantilla del drop-in, D-007 (propuesta, ⏸).

## 2026-11-17 · Cambio de planes (D-008) y Bloque 5 — OpenClaw
- Registrado el cambio en MISION_ARCH, DECISIONES (D-007 resuelta, D-008), PLAN y CLAUDE.md.
- Ollama: face no necesita `/opt/cuda` (`cuda` solo lo pide `ollama-cuda`; faster-whisper usa wheels con CUDA propio).
  `01-sistema.sh` ya no instala Ollama y lo desinstala si está; ufw siempre. ⏸ El usuario lo ejecuta con sudo.
- OpenClaw 2026.11.5 (`npm i -g --allow-scripts=openclaw`, prefijo `~/.local`). Submodule en `v2026.11.5`.
- Onboarding sin interacción: `--auth-choice anthropic-cli` reutiliza el login de Claude Code (plan Pro).
- Problema: `gateway install` falla ("Managed service artifacts changed during publication") si el drop-in ya existe;
  solución: instalar la unidad, parar, poner el drop-in, `daemon-reload`, arrancar. `sync-brain.sh` lo mantiene.
- El CLI de Claude funciona dentro del encierro (probado con `claude -p`). `~/.claude` queda accesible.
- La política por defecto de exec era `security=full, ask=off`: cerrada con la allowlist (`brain/config/exec-approvals.json`).
- `argPattern` no usa la bandera `u`: `\p{L}` no funciona → clases explícitas con acentos.
- Hyprland 0.57 usa config Lua: `hyprctl dispatch exec` falla; se usa `hyprctl dispatch 'hl.dsp.exec_cmd("…")'`.
  Las apps se lanzan como hijas de Hyprland (fuera del encierro) para que Chrome vea su perfil.
- `openclaw config get` redacta secretos: el token se lee del JSON con jq. Token en `.env` (600, 48 caracteres).
- Fable 5.2 → "out of usage credits" en Pro; primary Opus 5.5. OpenClaw ya intentó el fallback por sí solo en ese
  error (falló solo porque Codex aún no tiene login) → el failover nativo salta con límites de uso.
- Pruebas por curl: 401 sin token; `/v1/models` con `openclaw/jarvis`; saludo en español; "abre la calculadora de
  libreoffice" → Calc abierto; receta de tortilla → `~/Documentos/Jarvis/Receta tortilla de patatas.docx` abierto en
  Writer (26 s); aislamiento: read fuera del workspace y exec fuera de la allowlist, denegados.
- Falta: ⏸ login de Codex; prueba de failover con GPT; face.

## 2026-11-17 · Bloque 6 — face en Linux + puente
- venv (uv, 3.11): torch 2.15 CPU, faster-whisper con cuBLAS/cuDNN de pip (2,1 GB), kokoro, openwakeword, total 3,9 GB.
- Pruebas reales: Kokoro `em_alex` en español (0,28 s en caliente) → Whisper `large-v3-turbo` en CUDA transcribe
  la frase exacta (0,48 s en caliente; VRAM total 1,6 GB con el escritorio). "Hey Jarvis" sintético: 1,00.
- Falta `websockets` en el venv: uvicorn no atendía el WebSocket del HUD → añadido a requirements.
- HUD en vivo: sin token 401, Host ajeno 421, token → cookie y redirección; WS sin cookie rechazado; orden escrita
  por WS → Claude → respuesta hablada. `jarvis-face.service` habilitado (linger: arranca solo).
- El usuario reejecutó `01-sistema.sh`: ollama/cuda fuera, ufw instalado pero **inactivo**: el kernel en marcha
  (7.3.4-arch1-1) ya no tiene módulos (instalado arch1-2) → hace falta reiniciar.
- doctor.sh: corregidos falsos rojos de loopback (la regex miraba la columna del par remoto).
- Pendiente: ⏸ login de Codex, ⏸ reinicio + ufw, ⏸ prueba de voz, prueba de failover con GPT.

## 2026-11-17 · Bloque 7 — Voz real: micrófono, Bluetooth, ducking, atajo
- Tras reiniciar: ufw activo y uinput cargado. face arrancó, pero no oía y la música sonaba distorsionada.
- Diagnóstico (wpctl/pw-top/pactl): los audífonos BT "Alaxe" estaban en HFP (mono, 16 kHz, quantum 2048) porque face
  abría su micrófono (fuente por defecto, **silenciada**) por pipewire-alsa (PortAudio); Spotify salía en mono por HFP.
  Sin xruns. Graph a 48 kHz, sin latencia forzada.
- El micrófono del portátil estaba al 100 % = +60 dB (Base Volume 10 % = 0 dB) → todo a −32768. Ahora en 20 %.
- Hecho: `mic.py` (un `pw-record` compartido), `wake.py`/`stt.py` sobre él (umbrales adaptativos al ruido),
  autoswitch BT apagado y A2DP restaurado, `ducking.py` (probado: baja al 20 % y restaura exacto, también tras una
  "caída"), atajo Super+J (socket Unix), `hf_offline.py` (sin avisos de HF al arrancar).
- Problemas: el ducking bajaba la propia voz (pipewire-alsa no publica el PID) y WirePlumber memorizó ese 4 % → se
  nombra el stream con `PIPEWIRE_PROPS` y se devolvió al 100 %.
- Pruebas: "Hey Jarvis" sintético por los altavoces → micrófono: 0,995 (la cadena funciona). Tomas del señor: máx 0,056
  (sin confirmar que hablara en la ventana; ruido de la sala variable, 0,008–0,066 RMS). Falta calibrar el umbral con él.

## 2026-11-17 · Bloque 7b — Voz natural (prioridad del señor)
- Journal: "hola, qué tal" no falló: el diseño era de un solo turno. 1,5 s de "¿Sí, señor?" antes de escuchar; cerebro
  7,6 s (Opus). El micrófono estaba **silenciado** (ceros): face ahora avisa con notificación tras 4 s de ceros.
- Bug de origen: `python -m jarvis.main` + `from jarvis.main import …` en web.py → dos copias del módulo; el HUD no
  recibía eventos de voz. Corregido. El HUD comparaba textos en inglés: ahora hay mensaje `state` e insignia
  "EN CONVERSACIÓN".
- Hecho: vad.py, nombre.py, frases.py, conversacion.py, tts.py (motor intercambiable, stream persistente, voz por
  oraciones con el 1.er trozo cortado en la primera coma), brain.py en streaming (SSE). Sin openWakeWord ni PyAudio.
- Arnés con audio inyectado (cerebro y voz reales), 3 turnos: frase sin nombre ignorada; "Jarvis, ¿estás despierto?"
  → local en 1,13 s desde que calla (fin de frase 0,67 + STT 0,41); "¿qué hora es?" y "dame una idea para cenar" sin
  nombre; "Jarvis, gracias, eso es todo" → despedida y espera. Con orden: voz a los 3,3 s del fin de frase.
- Sonnet principal (D-011). AEC evaluado y descartado (D-010). Muestras de voz en tmp/voces/ (⏸ elección).
- Por el aire (altavoz → micrófono del portátil) la señal llega muy degradada: no sirve para autopruebas.

## 2026-11-17 · Voz Jorge, refuerzos a–e y failover a GPT
- Voz: Edge `es-MX-JorgeNeural` (-8 %, -2 Hz) con respaldo Piper `es_MX-claude-high` (probado con un fallo simulado:
  0,57 s y registrado), Azure preparado (D-012). 30 frases regeneradas con Jorge (60 s).
- Prueba de 3 turnos: en 5 min no hubo activación; la sala tenía conversación (~40 frases sin nombre, ignoradas). No se
  sabe si el señor llegó a hablar → la traza `debug` ahora da el parecido con «jarvis» (sin contenido). ⏸ repetir.
- Refuerzos a–e (D-013): secretos a ~/.config/jarvis (repo sin .env), drop-in ampliado, pruebas desde el namespace del
  gateway y con el agente. `openclaw config patch` falla con el gateway en marcha (EROFS, buscado) → sync-brain lo para.
- Failover (D-014): respaldo gpt-5.6-terra; agente jarvis estricto; face anuncia el cambio. Durante el sondeo de
  modelos el proveedor openai entró en cooldown (model_not_found repetido) → esperar y probar de uno en uno.
- doctor.sh: todo en verde (incluidos refuerzos y respaldo).
- Conversación real de 18 turnos (abierta con Super+J por Claude para comprobar los hilos; se respondió de viva voz):
  voz típica a los 3,8–4,9 s del fin de frase (VAD 0,67 + STT 0,43 + cerebro 1,1 + Edge ~1,5). Dos turnos tardaron
  24 y 34 s: el cerebro mandaba una frase sin punto y luego usaba una herramienta → el divisor esperaba el punto.
  Arreglado: tras 0,7 s sin texto del cerebro se dice lo recibido (`tts.FLUSH`).
- Riesgo visto: en modo conversación se atiende a CUALQUIER voz de la sala (no solo la del señor). Propuesta:
  verificación de hablante o exigir el nombre si hay más voces (⏸ decisión).
- Activación por nombre aún sin confirmar con la voz del señor: en las ventanas de prueba nadie dijo «Jarvis»
  (parecido máximo 0,44).

## 2026-11-18 · Privacidad, verificación de hablante, música, enrutado
- Prueba de 3 turnos del señor: activación por nombre OK ("Jarvis, ¿estás despierto?" → local en 1,12 s). "Hasta
  mañana" no cerraba (añadido). Clima con ciudad: voz a los 12 s. Se colaron frases de terceros en la conversación y la
  música no volvió a su volumen al cerrar (arreglado, D-016).
- Borrado a petición del señor (conversación de 18 turnos y frases de terceros): sesión `face:jarvis` de OpenClaw
  (+ su copia archivada .zst y memorias indexadas), su transcripción del CLI de Claude
  (~/.claude/projects/-home-wil--openclaw-workspace-jarvis/21d91dcd….jsonl) y VACUUM de las dos bases SQLite;
  verificado sin rastro. El journal de usuario (root) necesita sudo: ⏸.
- Regla nueva: no abrir sesiones de escucha sin que el señor esté probando.
- Verificación de hablante (D-015), música y volumen locales (D-016), enrutado charla/trabajo (D-017).
- `scripts/revisar-push.sh` + hook pre-push: probado con un secreto real, un .wav y una línea de log (los tres
  detectados). Arreglado un fallo de pipefail que lo hacía pasar por alto secretos.
- Un test llevaba la ciudad del señor: cambiada y commit reescrito antes del push (sin rastro en el historial).

## 2026-11-18 · Spotify sin credenciales, prosa y ubicación
- Spotify (D-018): el señor tiene Spotify Free y la API en Development Mode ya exige Premium (y perdió top tracks).
  Probado en la app: `spotify:search:` abre la búsqueda, pero lo útil es la búsqueda rápida (Ctrl+K) con Shift+Enter =
  reproducir; con `artist:X` solo salen temas del artista. Hecho con ydotool + portapapeles (teclado latam) y
  restaurando foco y portapapeles. Pruebas reales: Cerati, Soda Stereo y Enanitos Verdes sonaron (y se pausaron).
  `ydotool.service` estaba deshabilitado: habilitado; doctor.sh e install-face.sh lo cubren.
- Prosa (D-019): mensaje `system` por petición (OpenClaw lo convierte en instrucciones extra del turno) + filtro de
  Markdown al vuelo antes de la voz. GPT y Sonnet contestaron en prosa a "tres ideas para cenar con los pasos".
- Ubicación (D-020): ciudad del señor (sacada de sus propias órdenes de clima en el registro de face) en MEMORY.md del
  workspace del agente. Clima sin ciudad → responde con la suya. Sesión de prueba `prueba-prosa` borrada; su índice
  de memoria (`openclaw memory forget`) solo se puede borrar con el gateway parado: pendiente, sin importancia.
- Tests: 94 en verde.
- Pendiente: ⏸ prueba de voz con la verificación de hablante (enrolar primero) → después, push.

## 2026-11-18 · Push por SSH y limpieza de la sesión de prueba
- `ssh -T` saluda al usuario de GitHub → remoto `origin` a SSH. `revisar-push.sh` (y el hook): nada sensible en 25
  commits → push `029e820..ad3f19c`.
- Sesión `prueba-prosa`: `openclaw memory forget` con el gateway parado → 0 filas indexadas (nada que borrar). Quedaba su
  transcripción archivada (archivo `.deleted….zst` y fila en `session_transcript_archives`): borradas, VACUUM e
  `integrity_check` ok; gateway arrancado y `/v1/models` responde. Quedan solo eventos de auditoría (metadatos, sin
  contenido) y la lápida de memoria (id).
- Visto de paso: sigue en `session_transcript_archives` el archivo de la sesión `face:jarvis` borrada el 17/11 (la
  conversación de 18 turnos). ⏸ decidir si se borra también.
- La huella de voz NO está en ~/.config/jarvis/voz.npz (ni en otro sitio): face sigue con la verificación desactivada.

## 2026-11-18 · Sesión de audio (en curso): filtro del PC, interrupción, cierre, latencia, fluidez
- Verificación de hablante apagada por decisión del señor (`hablante.activo: false`); código conservado (D-015).
- Cancelador de eco: envoltorio C de WebRTC AEC3 (`face/native/aec.cc`, la librería de PipeWire) cargado por ctypes
  (`jarvis/eco.py`). Sintético: −32 dB. Detección de audífonos (BT/toma de auriculares; altavoz BT no cuenta).
- `jarvis/mic.py` reescrito: micrófono + monitor de la salida por defecto, AEC en vivo, anillo de 30 s del original
  por índice de muestra; las frases llevan su índice (`Utterance.i0`). Interrupción por voz (`barge_in: auto`) que
  corta la voz y la petición al cerebro. Pendiente de medir con grabaciones reales (⏸ el señor da la señal).
- Cierre (D-022): despedidas por "solo quedan expresiones de cierre" (adiós, ya, gracias, termina, cierra la
  conversación, por favor…); 2 s sin escuchar y cola vaciada; Super+J reactiva.
- Latencia (D-024): Edge con conexión persistente precalentada al empezar a hablar: frase completa en 0,35–0,4 s
  (antes 1,3–1,6 s; con el servicio lento 0,8–1,6 frente a 1,8–2,3 s). Edge mete 0,23 s de silencio delante y
  0,9 s detrás: recortados. Fin de frase 0,45 s + espera de 1,5 s si la frase queda a medias ("y…", "de…").
- Cerebros (para el bloque 5): primer token con el agente jarvis: gpt-5.6-luna 1,4–1,7 s (y ratos de 4–10 s),
  terra 2,2–5,8 s, gpt-6-luna 5,3 s; Sonnet 1,1–2,4 s; Haiku 0,6–1,9 s. Agente ligero `charla` con Haiku:
  0,63–0,73 s. `charla` con ChatGPT no arranca: sin login propio y la herencia del OAuth de jarvis falla
  (McpConnectionAuthorityError) → revertida; haría falta ⏸ login del señor en ese agente.
- Vocabulario privado de Whisper (`~/.config/jarvis/vocabulario.txt`, 600): 88 artistas (caché de letras del
  escritorio) y 51 aplicaciones; `scripts/jarvis-vocabulario`. Pendiente medir si ayuda.
- Borrado: copia archivada de la conversación de 18 turnos (fila + VACUUM), transcripción de la sesión del CLI de
  Claude del 17/11 tachada (443 líneas de log y 50 textos), caché /tmp/openclaw de la sesión de prueba.

## 2026-11-18 (tarde) · Trabajo en silencio: Spotify, navegador, Canva, imágenes
- Sesión de audio aparcada como estaba (ver PLAN, bloque 11). Salida de audio en silencio durante las pruebas.
- Spotify (D-025): diagnóstico con el registro de face y bisect; arreglado, 10+ tests de regresión, probado en real
  (abierto y cerrado). Allowlist de playerctl alineada con AGENTS.md (`--player=` y `volume`). face sigue con el
  código anterior hasta que el señor lo reinicie.
- Navegador propio (D-026): perfil `jarvis` aislado, envoltorio `jarvis-chrome`, sin evaluate ni red local, perfiles
  `user`/`chrome` neutralizados. Probado por texto con el agente (Hacker News). `scripts/jarvis-navegador` para que el
  señor inicie sesión; doctor.sh lo comprueba. Sesión de prueba `prueba-navegador` (solo un titular) sin borrar.
- Tras el reinicio, ydotool había caído (arrancó antes de la ACL de /dev/uinput → start-limit-hit). Drop-in
  `scripts/systemd/ydotool.service.d/` que reintenta cada 2 s; instalado y en install-face.sh. doctor.sh en verde.
