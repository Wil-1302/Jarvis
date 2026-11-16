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
