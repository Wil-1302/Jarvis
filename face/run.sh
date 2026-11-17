#!/usr/bin/env bash
# Lanza JARVIS face con las librerías CUDA de pip (cuBLAS/cuDNN) en el LD_LIBRARY_PATH (sin /opt/cuda).
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
[[ -x $PY ]] || { echo "Falta el venv: ejecuta scripts/install-face.sh" >&2; exit 1; }
NV="$($PY -c 'import nvidia, os; print(os.path.dirname(nvidia.__path__[0]))' 2>/dev/null || true)/nvidia"
for d in cublas cudnn cuda_nvrtc; do [[ -d $NV/$d/lib ]] && LD_LIBRARY_PATH="$NV/$d/lib:${LD_LIBRARY_PATH:-}"; done
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" PYTHONUNBUFFERED=1
exec "$PY" -m jarvis.main "$@"
