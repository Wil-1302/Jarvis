#!/usr/bin/env bash
# JARVIS — Bloque 2: paquetes del sistema (Arch Linux).
# Uso:  sudo bash scripts/arch/01-sistema.sh
# Idempotente: se puede ejecutar varias veces. Explica qué hará y pide confirmación.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Ejecútalo con: sudo bash $0" >&2; exit 1
fi
USUARIO="${SUDO_USER:-}"
if [[ -z "$USUARIO" || "$USUARIO" == "root" ]]; then
  echo "Ejecútalo con sudo desde tu usuario normal (no como root directo)." >&2; exit 1
fi

# Paquetes de los repos oficiales (verificados en extra/core el 2026-11-16).
BASE=(base-devel git openssh jq ripgrep ffmpeg xdg-utils uv pacman-contrib)  # pacman-contrib: paccache
NODE=(nodejs npm)                       # Node 26 del sistema (D-006)
AUDIO_VOZ=(portaudio espeak-ng)         # espeak-ng: fonemas para Kokoro en español
ESCRITORIO=(wl-clipboard playerctl libnotify brightnessctl at-spi2-core ydotool)
OFIMATICA=(libreoffice-fresh libreoffice-fresh-es)

cat <<EOF
================ JARVIS · 01-sistema.sh ================
Usuario destino: $USUARIO

Este script va a:
  1. Actualizar el sistema e instalar lo que falte (pacman -Syu --needed):
       ${BASE[*]}
       ${NODE[*]}
       ${AUDIO_VOZ[*]}
       ${ESCRITORIO[*]}
       ${OFIMATICA[*]}
       (Sin Ollama ni CUDA: D-008. faster-whisper trae sus librerías CUDA por pip.)
  2. Limpieza de una versión anterior de este script: si existen ollama/ollama-cuda/cuda
     instalados por él, los desinstala (pacman -Rns) junto con su drop-in.
  3. ydotool: asegurar que el módulo uinput se cargue al arrancar
     (/etc/modules-load.d/jarvis-uinput.conf). El acceso a /dev/uinput ya lo da la
     ACL de tu sesión (uaccess); NO se te añade al grupo 'input'.
  4. loginctl enable-linger $USUARIO (servicios de usuario sin sesión abierta).
  5. ufw denegando todo lo entrante y permitiendo lo saliente.
No toca nada más. No usa AUR.
=========================================================
EOF
read -r -p "¿Continuar? [s/N] " r; [[ "$r" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }

echo; echo ">> [1/5] pacman -Syu --needed ..."
PKGS=("${BASE[@]}" "${NODE[@]}" "${AUDIO_VOZ[@]}" "${ESCRITORIO[@]}" "${OFIMATICA[@]}" ufw)
pacman -Syu --needed --noconfirm "${PKGS[@]}"

echo; echo ">> [2/5] Limpieza de Ollama/CUDA (D-008) ..."
VIEJOS=()
for p in ollama-cuda ollama-vulkan ollama; do pacman -Qq "$p" &>/dev/null && VIEJOS+=("$p"); done
if ((${#VIEJOS[@]})); then
  systemctl disable --now ollama.service 2>/dev/null || true
  pacman -Rns --noconfirm "${VIEJOS[@]}"   # -s arrastra cuda si nadie más lo necesita
  rm -rf /etc/systemd/system/ollama.service.d
  systemctl daemon-reload
else
  echo "   nada que limpiar."
fi

echo; echo ">> [3/5] uinput al arranque ..."
echo uinput > /etc/modules-load.d/jarvis-uinput.conf
modprobe uinput

echo; echo ">> [4/5] linger para $USUARIO ..."
loginctl enable-linger "$USUARIO"

echo; echo ">> [5/5] ufw ..."
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
systemctl enable --now ufw.service

echo
echo "================ Verificación ================"
printf 'ollama:   '; pacman -Qq ollama &>/dev/null && echo "SIGUE INSTALADO" || echo "no instalado (ok)"
printf 'cuda:     '; pacman -Qq cuda &>/dev/null && echo "sigue (lo pide otro paquete)" || echo "no instalado (ok)"
printf 'linger:   '; loginctl show-user "$USUARIO" -p Linger --value
printf 'uinput:   '; lsmod | grep -qw uinput && echo cargado || echo NO
printf 'node:     '; node --version
for c in playerctl espeak-ng soffice; do printf '%-9s ' "$c:"; command -v "$c" >/dev/null && echo ok || echo FALTA; done
printf 'ufw:      '; ufw status | head -1
echo "Listo. Vuelve con Claude y dile que terminó."
