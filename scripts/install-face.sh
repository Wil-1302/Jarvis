#!/usr/bin/env bash
# JARVIS — instala el venv de face (Python 3.11, uv). Idempotente. Sin sudo.
# torch CPU (Kokoro en CPU) + cuBLAS/cuDNN por pip para faster-whisper en GPU. Descarga ~1,5 GB la primera vez.
set -euo pipefail
cd "$(dirname "$0")/../face"
echo ">> venv Python 3.11 en face/.venv"; [[ -x .venv/bin/python ]] || uv venv -q --python 3.11 .venv
echo ">> torch (CPU)";  uv pip install -q --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch
echo ">> dependencias (requirements-linux.txt)"; uv pip install -q --python .venv/bin/python -r requirements-linux.txt
echo ">> unidad systemd de usuario"; install -Dm644 ../scripts/systemd/jarvis-face.service ~/.config/systemd/user/jarvis-face.service
systemctl --user daemon-reload

echo ">> WirePlumber: audífonos Bluetooth siempre en A2DP (sin autoswitch a HSP/HFP)"
install -Dm644 ../scripts/wireplumber/51-jarvis-bluetooth.conf ~/.config/wireplumber/wireplumber.conf.d/51-jarvis-bluetooth.conf
wpctl settings bluetooth.autoswitch-to-headset-profile false >/dev/null 2>&1 || true

MIC=alsa_input.pci-0000_05_00.6.analog-stereo
if pactl get-source-volume "$MIC" >/dev/null 2>&1; then
  v=$(pactl get-source-volume "$MIC" | grep -oE '[0-9]+%' | head -1 | tr -d %)
  # En este DMIC el 0 dB del hardware es el 10 % del control: al 100 % (+60 dB) solo da saturación.
  if (( v > 50 )); then echo ">> micrófono del portátil: ${v}% → 20% (+18 dB)"; pactl set-source-volume "$MIC" 20%; fi
fi

echo ">> atajo global Super+J (Hyprland/Caelestia: ~/.config/caelestia/hypr-user.lua)"
HU=~/.config/caelestia/hypr-user.lua
if [[ -f $HU ]] && ! grep -q jarvis-escucha "$HU"; then
  printf '\n-- JARVIS: escuchar sin wake word (si está hablando, lo detiene).\nhl.bind("SUPER + J", hl.dsp.exec_cmd(os.getenv("HOME") .. "/Proyectos/Jarvis/scripts/bin/jarvis-escucha"))\n' >> "$HU"
  hyprctl reload >/dev/null 2>&1 || true
fi
echo "Listo. Arranque: scripts/start-all.sh"
