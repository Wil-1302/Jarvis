#!/usr/bin/env bash
# JARVIS — diagnóstico. SOLO LECTURA: no cambia nada. No muestra secretos.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ok() { printf '  \e[32m✔\e[0m %s\n' "$*"; }; ko() { printf '  \e[31m✘\e[0m %s\n' "$*"; FALLOS=$((FALLOS+1)); }
FALLOS=0
chk() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else ko "$d"; fi; }
echo "Cerebro (OpenClaw)"
chk "openclaw instalado ($(openclaw --version 2>/dev/null | head -1))" command -v openclaw
chk "gateway activo" systemctl --user is-active openclaw-gateway.service
chk "gateway solo en loopback" bash -c "ss -tlnH 'sport = :18789' | awk '{print \$4}' | grep -q '^127.0.0.1:' && ! ss -tlnH 'sport = :18789' | awk '{print \$4}' | grep -qE '^(0\.0\.0\.0|\*|\[::\]):'"
chk "encierro systemd aplicado" bash -c "systemctl --user show openclaw-gateway -p DropInPaths | grep -q jarvis-aislamiento"
chk "login de Claude Code" bash -c "claude auth status --text | grep -qi 'login method'"
chk "token del gateway en .env (600)" bash -c "[[ \$(stat -c %a '$REPO/.env') == 600 ]] && grep -q '^OPENCLAW_GATEWAY_TOKEN=.\{32,\}' '$REPO/.env'"
TOKEN="$(grep -m1 '^OPENCLAW_GATEWAY_TOKEN=' "$REPO/.env" 2>/dev/null | cut -d= -f2-)"
chk "/v1/models lista openclaw/jarvis" bash -c "curl -sf -H 'Authorization: Bearer $TOKEN' http://127.0.0.1:18789/v1/models | grep -q openclaw/jarvis"
chk "sin token → 401" bash -c "[[ \$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18789/v1/models) == 401 ]]"
chk "respaldo Codex con login" bash -c "openclaw models list --provider openai 2>/dev/null | grep -q 'gpt-6-astra.*yes'"
echo "Cara (face)"
chk "venv de face" test -x "$REPO/face/.venv/bin/python"
chk "jarvis-face activo" systemctl --user is-active jarvis-face.service
chk "HUD solo en loopback" bash -c "ss -tlnH 'sport = :7860' | awk '{print \$4}' | grep -q '^127.0.0.1:' && ! ss -tlnH 'sport = :7860' | awk '{print \$4}' | grep -qE '^(0\.0\.0\.0|\*|\[::\]):'"
chk "HUD sin token → 401" bash -c "[[ \$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:7860/api/providers) == 401 ]]"
echo "Sistema"
chk "sin Ollama/CUDA (D-008)" bash -c "! pacman -Q ollama >/dev/null 2>&1 && ! pacman -Q cuda >/dev/null 2>&1"
chk "ufw activo" systemctl is-active ufw.service
chk "linger" bash -c "loginctl show-user $USER -p Linger | grep -q yes"
chk "GPU NVIDIA visible" nvidia-smi -L
echo; ((FALLOS==0)) && echo "Todo en verde." || echo "$FALLOS comprobación(es) en rojo."
exit $((FALLOS>0))
