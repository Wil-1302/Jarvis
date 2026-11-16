# Entorno Arch Linux (auditoría del 2026-11-16, solo lectura)

## Sistema

| Elemento | Valor | Nota |
|---|---|---|
| Distro | Arch Linux (rolling), kernel 7.3.4-arch1-1 | |
| Escritorio | Hyprland 0.57.2 (shell quickshell) | |
| Sesión | `wayland` (`WAYLAND_DISPLAY=wayland-1`) | Nada de X11: usar wl-clipboard, ydotool, portales |
| Shell | bash (`~/.bashrc` ya añade `~/.local/bin` al PATH) | |
| Host / usuario | `archwil` / `wil` (grupos: `wil`, `wheel`) | |

## GPU

- `lspci` solo ve **una** GPU: NVIDIA AD107M **RTX 4050 Laptop, 6141 MiB**, driver `nvidia-open 620.70.06`, CUDA UMD 13.5.
- La iGPU AMD (Rembrandt) **no aparece**: el portátil (Lenovo) está con el **MUX en modo dGPU/discreto**.
  No hay gráficos híbridos activos; no hace falta PRIME offload ni `__NV_PRIME_RENDER_OFFLOAD`.
  Si algún día se cambia a modo híbrido en la BIOS, revisar que Ollama/Whisper sigan en la NVIDIA.
- La NVIDIA también pinta el escritorio: **~1,6 GB de VRAM ya están ocupados** (Hyprland, Chrome, wallpaper engine).
  Presupuesto real para Jarvis: **~4,5 GB** (LLM local + Whisper). Esto condiciona el Bloque 4 y el modelo de STT.
- `nvcc`/paquete `cuda` no instalado (no es necesario para Ollama-Vulkan ni para las wheels de faster-whisper).

## Memoria y disco

- RAM: 23 GiB útiles (24 GB) + 4 GiB de zram.
- Disco: `/` y `/home` en la misma partición ext4 de 115,8 GB: **25 GB libres (78 % usado)**.
  `~/.cache` ocupa **28 GB** (candidato a limpieza; decisión del usuario).
- Hay particiones NTFS de Windows (359 GB) sin montar.

## Audio

- PipeWire 1.6.11 + WirePlumber.
- Salidas: Ryzen HD Audio (analógica) y **Alaxe (Bluetooth, salida por defecto)**.
- Entradas: micrófono analógico Ryzen HD Audio y `bluez_input` (micrófono del Bluetooth, fuente por defecto).
  Para STT conviene el micrófono interno (el perfil HFP del Bluetooth degrada la calidad y el audio de salida).
- `arecord` (alsa-utils) no instalado; no es imprescindible (`pw-record` sirve).

## Herramientas

| Herramienta | Estado |
|---|---|
| git 2.56.1, openssh 10.6, base-devel | ✅ |
| Python 3.14.10 (sistema), uv 0.13.8, Python 3.12 gestionado por uv | ✅ — **falta Python 3.11** (Bloque 3) |
| Node **26.13.1** (`extra/nodejs`), npm 12.2.2, pnpm 12.20 | ✅ OpenClaw acepta `>=24.16 <25 \|\| >=26.1` y marca Node 26 como **recomendado** |
| `npm config get prefix` | `/usr` → **hay que pasarlo a `~/.local`** (Bloque 3) |
| yay 13.1 (AUR) | ✅ — paru no |
| jq, ripgrep, ffmpeg 9, xdg-utils, wl-clipboard, libnotify, brightnessctl, at-spi2-core, portaudio | ✅ |
| ydotool 1.0.4 | ✅ instalado; servicio de usuario `ydotool.service` existe pero **inactivo** |
| `/dev/uinput` | `root:input 660` + ACL `user:wil:rw` (uaccess de la sesión). No hace falta meter al usuario en `input` |
| Spotify | ✅ cliente de escritorio ya instalado (`spotify 1:1.3.8.620`, AUR) — resuelve la pregunta del Bloque 9.2 |
| Ollama | ❌ falta (repos: `ollama` + `ollama-cuda` o `ollama-vulkan`) |
| playerctl, espeak-ng, libreoffice-fresh(-es) | ❌ faltan |
| docker / podman | ❌ (no se necesitan por ahora) |
| ufw / firewalld | ❌ ningún firewall activo |
| gh (GitHub CLI), openclaw | ❌ |

## Red (puertos en escucha)

- `127.0.0.1:5432` y `[::1]:5432`: PostgreSQL local (ya existente).
- `0.0.0.0:57621`: Spotify (Spotify Connect/descubrimiento local). Expuesto a la LAN; sin firewall.

## Identidad / git

- **No hay `~/.ssh`** (ni llave ni known_hosts) → crear ed25519 en el Bloque 3.
- **No hay `~/.gitconfig`** → hay que definir `user.name` y `user.email` (Bloque 3).
- Remoto actual del repo: HTTPS (clonado así); pasar a SSH en el Bloque 3.

## Paquetes verificados en los repos (2026-11-16)

| Paquete | Repo | Versión | Descarga | Nota |
|---|---|---|---|---|
| `ollama` | extra | 0.40.16 | 19 MB | |
| `ollama-cuda` | extra | 0.40.16 | 396 MB | **depende de `cuda` (2,43 GiB de descarga, 5,2 GiB instalado)** → ⏸ regla de >2 GB |
| `ollama-vulkan` | extra | 0.40.16 | 5 MB | Alternativa sin CUDA (usa `vulkan-icd-loader`, ya instalado) |
| `nodejs-lts-krypton` | extra | 24.22.3 | | Entra en conflicto con `nodejs` 26 instalado |
| `espeak-ng` | extra | 1.52.0 | | |
| `playerctl` | extra | 2.4.1 | | |
| `libreoffice-fresh` / `-es` | extra | 26.8.2 | ~460 MB inst. | |
| `ufw` | extra | 0.36.2 | | Opcional |
| `python-pyaudio` | — | no existe | | PyAudio irá por pip en el venv (portaudio ya está) |

## Qué falta (resumen)

1. Sistema (sudo, Bloque 2): Ollama (+ backend GPU), playerctl, espeak-ng, LibreOffice + español, linger, ufw opcional.
2. Usuario (Bloque 3): Python 3.11, prefijo npm en `~/.local`, llave SSH, git config.
3. Espacio en disco: con 25 GB libres, CUDA (5,2 GB) + modelos + venv de face (torch/CUDA ~5 GB) quedan justos.
