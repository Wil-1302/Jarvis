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
echo "Listo. Arranque: scripts/start-all.sh"
