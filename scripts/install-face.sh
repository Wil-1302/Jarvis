#!/usr/bin/env bash
# JARVIS — instala el venv de face (Python 3.11, uv). Idempotente. Sin sudo.
# torch CPU (Kokoro en CPU) + cuBLAS/cuDNN por pip para faster-whisper en GPU. Descarga ~1,5 GB la primera vez.
set -euo pipefail
cd "$(dirname "$0")/../face"
echo ">> venv Python 3.11 en face/.venv"; [[ -x .venv/bin/python ]] || uv venv -q --python 3.11 .venv
echo ">> torch (CPU)";  uv pip install -q --python .venv/bin/python --index-url https://download.pytorch.org/whl/cpu torch
echo ">> dependencias (requirements-linux.txt)"; uv pip install -q --python .venv/bin/python -r requirements-linux.txt
echo ">> voz Piper de respaldo (es_MX-claude-high, ~63 MB) en ~/.local/share/jarvis/piper"
PIPER=~/.local/share/jarvis/piper; install -d "$PIPER"
[[ -f $PIPER/es_MX-claude-high.onnx ]] || .venv/bin/python -m piper.download_voices --download-dir "$PIPER" es_MX-claude-high
echo ">> modelo de verificación de hablante (NeMo TitaNet small, 40 MB) en ~/.local/share/jarvis/voz-modelos"
VM=~/.local/share/jarvis/voz-modelos; install -d "$VM"; M=$VM/nemo_en_titanet_small.onnx
[[ -f $M ]] || curl -fsSL -o "$M" "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/nemo_en_titanet_small.onnx"
echo "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e  $M" | sha256sum -c --quiet || { echo "hash del modelo incorrecto" >&2; rm -f "$M"; exit 1; }
echo ">> cancelación de eco (WebRTC AEC3 del sistema, la de PipeWire) → native/libjarvis_aec.so (D-021)"
g++ -O2 -shared -fPIC -std=c++17 native/aec.cc $(pkg-config --cflags --libs webrtc-audio-processing-1) -o native/libjarvis_aec.so
echo ">> hook pre-push (scripts/revisar-push.sh)"; printf '#!/usr/bin/env bash\nexec "$(git rev-parse --show-toplevel)/scripts/revisar-push.sh"\n' > ../.git/hooks/pre-push; chmod +x ../.git/hooks/pre-push
echo ">> secretos fuera del repo (refuerzo a)"; bash ../scripts/migrar-secretos.sh
echo ">> unidad systemd de usuario (arranca con graphical-session.target, no con linger)"
install -Dm644 ../scripts/systemd/jarvis-face.service ~/.config/systemd/user/jarvis-face.service
systemctl --user daemon-reload
systemctl --user reenable jarvis-face.service   # mueve el enlace de default.target.wants a graphical-session.target.wants
echo ">> ydotool (teclas para la búsqueda de Spotify, D-018) con la sesión gráfica"
install -Dm644 ../scripts/systemd/ydotool.service.d/jarvis-arranque.conf ~/.config/systemd/user/ydotool.service.d/jarvis-arranque.conf
systemctl --user daemon-reload
systemctl --user disable ydotool.service 2>/dev/null || true   # fuera de default.target (linger)
systemctl --user add-wants graphical-session.target ydotool.service
systemctl --user start ydotool.service

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
