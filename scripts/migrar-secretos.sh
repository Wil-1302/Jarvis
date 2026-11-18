#!/usr/bin/env bash
# JARVIS — refuerzo a: mueve los secretos de face del .env del repo a ~/.config/jarvis/secrets.env (600).
# Idempotente. No muestra valores. El gateway no puede leer esa carpeta (InaccessiblePaths del drop-in).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS="${JARVIS_SECRETS:-$HOME/.config/jarvis/secrets.env}"
echo ">> carpeta $(dirname "$SECRETS") (700) y archivo (600)"
install -d -m 700 "$(dirname "$SECRETS")"; ( umask 077; touch "$SECRETS" ); chmod 600 "$SECRETS"
if [[ -f $REPO/.env ]]; then
  echo ">> copiando variables del .env del repo que falten (sin mostrarlas)"
  while IFS= read -r l; do
    [[ $l =~ ^([A-Z0-9_]+)=(.+)$ ]] || continue
    grep -q "^${BASH_REMATCH[1]}=" "$SECRETS" || printf '%s\n' "$l" >> "$SECRETS"
  done < "$REPO/.env"
  for k in $(grep -oE '^[A-Z0-9_]+=.' "$REPO/.env" | cut -d= -f1); do
    grep -q "^$k=." "$SECRETS" || { echo "   falta $k en $SECRETS: no borro el .env" >&2; exit 1; }
  done
  echo ">> todas las variables están en $SECRETS; borro $REPO/.env"
  rm -f "$REPO/.env"
else
  echo ">> no hay .env en el repo (ya migrado)"
fi
echo "   variables: $(grep -cE '^[A-Z0-9_]+=.' "$SECRETS")"
