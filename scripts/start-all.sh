#!/usr/bin/env bash
# JARVIS — arranca el cerebro (OpenClaw) y la cara (face) y abre el HUD con su token.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
echo ">> gateway de OpenClaw"; systemctl --user start openclaw-gateway.service
for _ in $(seq 30); do ss -tlnH 'sport = :18789' | grep -q 127.0.0.1 && break; sleep 1; done
echo ">> face"; systemctl --user start jarvis-face.service
for _ in $(seq 60); do ss -tlnH 'sport = :7860' | grep -q 127.0.0.1 && break; sleep 1; done
TOK="$(grep -m1 '^JARVIS_HUD_TOKEN=' "${JARVIS_SECRETS:-$HOME/.config/jarvis/secrets.env}" | cut -d= -f2-)"
[[ -n $TOK ]] && xdg-open "http://127.0.0.1:7860/?token=$TOK" >/dev/null 2>&1 &
systemctl --user --no-pager --lines=0 status openclaw-gateway.service jarvis-face.service | grep -E "●|Active:"
