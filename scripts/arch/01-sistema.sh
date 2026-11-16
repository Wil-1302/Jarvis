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
BASE=(base-devel git openssh jq ripgrep ffmpeg xdg-utils uv)
NODE=(nodejs npm)                       # Node 26 del sistema (D-006)
AUDIO_VOZ=(portaudio espeak-ng)         # espeak-ng: fonemas para Kokoro en español
ESCRITORIO=(wl-clipboard playerctl libnotify brightnessctl at-spi2-core ydotool)
OFIMATICA=(libreoffice-fresh libreoffice-fresh-es)
OLLAMA=(ollama)

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
       ${OLLAMA[*]} + backend de GPU (a elegir: CUDA o Vulkan)
  2. Ollama: servicio de sistema 'ollama' habilitado, escuchando SOLO en 127.0.0.1:11434
     (drop-in /etc/systemd/system/ollama.service.d/jarvis.conf).
  3. ydotool: asegurar que el módulo uinput se cargue al arrancar
     (/etc/modules-load.d/jarvis-uinput.conf). El acceso a /dev/uinput ya lo da la
     ACL de tu sesión (uaccess); NO se te añade al grupo 'input'.
  4. loginctl enable-linger $USUARIO (servicios de usuario sin sesión abierta).
  5. Opcional: ufw denegando todo lo entrante (se pregunta).
No toca nada más. No usa AUR.
=========================================================
EOF
read -r -p "¿Continuar? [s/N] " r; [[ "$r" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }

echo
echo "Backend de GPU para Ollama:"
echo "  1) CUDA   (ollama-cuda + cuda: ~2,8 GB de descarga, ~5,7 GB en disco; el más rápido)"
echo "  2) Vulkan (ollama-vulkan: 5 MB; algo más lento, sin dependencia de CUDA)"
read -r -p "Elige 1 o 2 [2]: " b
case "${b:-2}" in
  1) BACKEND=cuda;   OLLAMA+=(ollama-cuda) ;;
  2) BACKEND=vulkan; OLLAMA+=(ollama-vulkan) ;;
  *) echo "Opción no válida."; exit 1 ;;
esac

read -r -p "¿Activar ufw (deniega todo lo entrante, permite lo saliente)? [s/N] " u
UFW=no; [[ "$u" =~ ^[sS]$ ]] && UFW=si

echo; echo ">> [1/5] pacman -Syu --needed ..."
PKGS=("${BASE[@]}" "${NODE[@]}" "${AUDIO_VOZ[@]}" "${ESCRITORIO[@]}" "${OFIMATICA[@]}" "${OLLAMA[@]}")
[[ $UFW == si ]] && PKGS+=(ufw)
pacman -Syu --needed --noconfirm "${PKGS[@]}"

echo; echo ">> [2/5] Ollama ($BACKEND) en 127.0.0.1:11434 ..."
install -d -m 755 /etc/systemd/system/ollama.service.d
{
  echo "# Generado por JARVIS scripts/arch/01-sistema.sh"
  echo "[Service]"
  echo 'Environment="OLLAMA_HOST=127.0.0.1:11434"'
  [[ $BACKEND == vulkan ]] && echo 'Environment="OLLAMA_VULKAN=1"'
} > /etc/systemd/system/ollama.service.d/jarvis.conf
systemctl daemon-reload
systemctl enable --now ollama.service
systemctl restart ollama.service

echo; echo ">> [3/5] uinput al arranque ..."
echo uinput > /etc/modules-load.d/jarvis-uinput.conf
modprobe uinput

echo; echo ">> [4/5] linger para $USUARIO ..."
loginctl enable-linger "$USUARIO"

if [[ $UFW == si ]]; then
  echo; echo ">> [5/5] ufw ..."
  ufw default deny incoming
  ufw default allow outgoing
  ufw --force enable
  systemctl enable --now ufw.service
else
  echo; echo ">> [5/5] ufw: omitido."
fi

echo
echo "================ Verificación ================"
printf 'ollama:   '; systemctl is-active ollama.service
printf 'escucha:  '; ss -tlnH 'sport = :11434' | awk '{print $4}' | paste -sd' '
printf 'backend:  %s\n' "$BACKEND"
printf 'linger:   '; loginctl show-user "$USUARIO" -p Linger --value
printf 'uinput:   '; lsmod | grep -qw uinput && echo cargado || echo NO
printf 'node:     '; node --version
for c in playerctl espeak-ng soffice; do printf '%-9s ' "$c:"; command -v "$c" >/dev/null && echo ok || echo FALTA; done
[[ $UFW == si ]] && { printf 'ufw:      '; ufw status | head -1; }
echo "Listo. Vuelve con Claude y dile que terminó."
