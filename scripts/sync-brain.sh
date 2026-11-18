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

# Refuerzo d: el gateway tiene ~/.openclaw/openclaw.json en solo lectura, así que la config se aplica
# con el gateway PARADO (el CLI escribe desde fuera del encierro) y luego se vuelve a arrancar.
ESTABA=0; systemctl --user is-active -q openclaw-gateway.service && ESTABA=1
if ((ESTABA)); then
  paso "Parada del gateway (para aplicar la config desde fuera del encierro)"
  systemctl --user stop openclaw-gateway.service
  for _ in $(seq 20); do ss -tlnH 'sport = :18789' | grep -q . || break; sleep 0.5; done
fi
paso "Config de OpenClaw (brain/config/jarvis.patch.json5)"
openclaw config patch --file "$REPO/brain/config/jarvis.patch.json5" --dry-run >/dev/null
openclaw config patch --file "$REPO/brain/config/jarvis.patch.json5" >/dev/null && echo "   aplicada"
if ((ESTABA)); then
  systemctl --user start openclaw-gateway.service
  for _ in $(seq 30); do ss -tlnH 'sport = :18789' | grep -q 127.0.0.1 && break; sleep 1; done
fi

paso "Agente jarvis → $WS"
install -d -m 700 "$WS" "$WS/skills" "$WS/documentos"
for f in SOUL.md AGENTS.md IDENTITY.md USER.md; do install -m 600 "$REPO/brain/agent/$f" "$WS/$f"; echo "   $f"; done
[[ -f $WS/BOOTSTRAP.md ]] && rm -f "$WS/BOOTSTRAP.md" && echo "   BOOTSTRAP.md retirado (identidad ya definida)"

WSC="$HOME/.openclaw/workspace-charla"   # D-023: agente ligero de charla
paso "Agente charla → $WSC"
install -d -m 700 "$WSC"
for f in SOUL.md AGENTS.md; do install -m 600 "$REPO/brain/agent-charla/$f" "$WSC/$f"; echo "   $f"; done
install -m 600 "$REPO/brain/agent/IDENTITY.md" "$REPO/brain/agent/USER.md" "$WSC/"
[[ -f $WSC/BOOTSTRAP.md ]] && rm -f "$WSC/BOOTSTRAP.md"

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

SECRETS="${JARVIS_SECRETS:-$HOME/.config/jarvis/secrets.env}"   # refuerzo a: fuera del repo y del gateway
paso "Token del gateway → $SECRETS (permisos 600, sin mostrarlo)"
install -d -m 700 "$(dirname "$SECRETS")"; touch "$SECRETS"; chmod 600 "$SECRETS"
# `openclaw config get` devuelve el valor redactado: se lee directamente del archivo (600).
TOKEN="$(jq -r '.gateway.auth.token // empty' "$HOME/.openclaw/openclaw.json")"
[[ ${#TOKEN} -ge 32 ]] || { echo "   token no encontrado o no es un valor literal" >&2; exit 1; }
( umask 077; grep -v '^OPENCLAW_GATEWAY_TOKEN=' "$SECRETS" > "$SECRETS.tmp" || true
  printf 'OPENCLAW_GATEWAY_TOKEN=%s\n' "$TOKEN" >> "$SECRETS.tmp" ); mv "$SECRETS.tmp" "$SECRETS"
echo "   existe, ${#TOKEN} caracteres"
unset TOKEN

if ((RESTART)); then
  paso "Reinicio del gateway"
  systemctl --user restart openclaw-gateway.service
  for _ in $(seq 30); do ss -tlnH 'sport = :18789' | grep -q 127.0.0.1 && break; sleep 1; done
  printf '   %s · ' "$(systemctl --user is-active openclaw-gateway.service)"; ss -tlnH 'sport = :18789' | awk '{print $4}' | paste -sd' '
fi
echo; echo "Sincronización terminada."
