#!/usr/bin/env bash
# JARVIS — sincroniza el cerebro (agente, skills, config, aprobaciones, encierro) hacia ~/.openclaw.
# Idempotente. Muestra cada paso. No imprime secretos. Uso: scripts/sync-brain.sh [--no-restart]
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WS="$HOME/.openclaw/workspace-jarvis"
DROPIN_DIR="$HOME/.config/systemd/user/openclaw-gateway.service.d"
RESTART=1; [[ ${1:-} == --no-restart ]] && RESTART=0
paso() { printf '\n>> %s\n' "$*"; }

command -v openclaw >/dev/null || { echo "openclaw no está en el PATH" >&2; exit 1; }

paso "Config de OpenClaw (brain/config/jarvis.patch.json5)"
openclaw config patch --file "$REPO/brain/config/jarvis.patch.json5" --dry-run >/dev/null
openclaw config patch --file "$REPO/brain/config/jarvis.patch.json5" >/dev/null && echo "   aplicada"

paso "Agente jarvis → $WS"
install -d -m 700 "$WS" "$WS/skills" "$WS/documentos"
for f in SOUL.md AGENTS.md IDENTITY.md USER.md; do install -m 600 "$REPO/brain/agent/$f" "$WS/$f"; echo "   $f"; done
[[ -f $WS/BOOTSTRAP.md ]] && rm -f "$WS/BOOTSTRAP.md" && echo "   BOOTSTRAP.md retirado (identidad ya definida)"

paso "Skills → $WS/skills"
for d in "$REPO"/skills/*/; do
  [[ -f $d/SKILL.md ]] || continue
  n="$(basename "$d")"; rm -rf "${WS:?}/skills/$n"; cp -r "$d" "$WS/skills/$n"; echo "   $n"
done

paso "Aprobaciones de exec (brain/config/exec-approvals.json)"
openclaw approvals set --file "$REPO/brain/config/exec-approvals.json" >/dev/null && echo "   aplicadas"

paso "Encierro systemd del gateway"
install -d -m 755 "$DROPIN_DIR"
if ! cmp -s "$REPO/scripts/systemd/openclaw-gateway.service.d/jarvis-aislamiento.conf" "$DROPIN_DIR/jarvis-aislamiento.conf"; then
  install -m 644 "$REPO/scripts/systemd/openclaw-gateway.service.d/jarvis-aislamiento.conf" "$DROPIN_DIR/"
  systemctl --user daemon-reload; echo "   drop-in actualizado"
else echo "   sin cambios"; fi

paso "Token del gateway → $REPO/.env (permisos 600, sin mostrarlo)"
touch "$REPO/.env"; chmod 600 "$REPO/.env"
# `openclaw config get` devuelve el valor redactado: se lee directamente del archivo (600).
TOKEN="$(jq -r '.gateway.auth.token // empty' "$HOME/.openclaw/openclaw.json")"
[[ ${#TOKEN} -ge 32 ]] || { echo "   token no encontrado o no es un valor literal" >&2; exit 1; }
grep -v '^OPENCLAW_GATEWAY_TOKEN=' "$REPO/.env" > "$REPO/.env.tmp" || true
printf 'OPENCLAW_GATEWAY_TOKEN=%s\n' "$TOKEN" >> "$REPO/.env.tmp"; chmod 600 "$REPO/.env.tmp"; mv "$REPO/.env.tmp" "$REPO/.env"
echo "   existe, ${#TOKEN} caracteres"
unset TOKEN

if ((RESTART)); then
  paso "Reinicio del gateway"
  systemctl --user restart openclaw-gateway.service
  for _ in $(seq 30); do ss -tlnH 'sport = :18789' | grep -q 127.0.0.1 && break; sleep 1; done
  printf '   %s · ' "$(systemctl --user is-active openclaw-gateway.service)"; ss -tlnH 'sport = :18789' | awk '{print $4}' | paste -sd' '
fi
echo; echo "Sincronización terminada."
