#!/usr/bin/env bash
# JARVIS — instala los MCP de Google (D-029). Idempotente; muestra cada paso; no imprime secretos.
#   - calendario: @cocal/google-calendar-mcp 2.8.1 (lockfile en mcp/calendario/, npm ci --ignore-scripts)
#   - escuela:    mcp/escuela/servidor.py (nuestro, solo biblioteca estándar)
# Los dos corren como servicios de usuario en 127.0.0.1, fuera del encierro del gateway.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LIB="$HOME/.local/lib/jarvis-mcp/google-calendar"
G="$HOME/.config/jarvis/google"
U="$HOME/.config/systemd/user"
paso() { printf '\n>> %s\n' "$*"; }

paso "Carpeta de credenciales $G (700)"
install -d -m 700 "$HOME/.config/jarvis" "$G"; chmod 700 "$G"
if [[ -f $G/oauth-client.json ]]; then chmod 600 "$G/oauth-client.json"; echo "   cliente OAuth: existe ($(stat -c %a "$G/oauth-client.json"))"
else echo "   cliente OAuth: FALTA → guárdelo como $G/oauth-client.json (ver mcp/calendario.md)"; fi

paso "Paquete fijado → $LIB"
install -d -m 755 "$LIB"
if ! cmp -s "$REPO/mcp/calendario/package-lock.json" "$LIB/package-lock.json" || [[ ! -d $LIB/node_modules ]]; then
  cp "$REPO/mcp/calendario/package.json" "$REPO/mcp/calendario/package-lock.json" "$LIB/"
  (cd "$LIB" && npm ci --ignore-scripts --no-fund --no-audit --fetch-timeout=600000 --fetch-retries=5)
else echo "   sin cambios"; fi
echo "   versión: $(node -p "require('$LIB/node_modules/@cocal/google-calendar-mcp/package.json').version")"

paso "Unidades systemd de usuario"
for s in jarvis-calendario jarvis-escuela; do install -m 644 "$REPO/scripts/systemd/$s.service" "$U/"; echo "   $s.service"; done
systemctl --user daemon-reload
for s in jarvis-calendario jarvis-escuela; do systemctl --user enable -q "$s.service"; done
if [[ -f $G/oauth-client.json ]]; then
  systemctl --user restart jarvis-calendario.service jarvis-escuela.service
  sleep 2; for s in jarvis-calendario jarvis-escuela; do echo "   $s: $(systemctl --user is-active $s)"; done
else echo "   habilitadas; arrancarán cuando exista el cliente OAuth (vuelva a ejecutar este script)"; fi
echo; echo "Listo. Inicio de sesión (⏸ lo hace el señor):"
echo "   personal:      scripts/jarvis-google login personal"
echo "   institucional: scripts/jarvis-google login escuela"
