#!/usr/bin/env bash
# JARVIS — detiene la cara y el cerebro.
set -euo pipefail
systemctl --user stop jarvis-face.service openclaw-gateway.service
systemctl --user is-active jarvis-face.service openclaw-gateway.service || true
