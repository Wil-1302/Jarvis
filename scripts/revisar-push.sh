#!/usr/bin/env bash
# JARVIS — revisión antes de `git push` (también como hook .git/hooks/pre-push). Solo lectura.
# Repasa TODOS los commits que aún no están en el remoto (no solo el último) y falla si encuentra:
# audio o huellas de voz, transcripciones/logs, .env o secretos (patrones + los valores reales de
# ~/.config/jarvis/secrets.env y del token del gateway, comparados sin mostrarlos), o archivos > 5 MB.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO"
BASE="$(git rev-parse -q --verify '@{upstream}' 2>/dev/null || git rev-parse -q --verify origin/main 2>/dev/null || true)"
RANGO="${BASE:+$BASE..}HEAD"
N="$(git rev-list --count "$RANGO")"
echo ">> revisando $N commit(s) sin subir ($RANGO)"
MAL=0; mal() { printf '  \e[31m✘\e[0m %s\n' "$*"; MAL=1; }
FILES="$(git log --format= --name-only --diff-filter=AM "$RANGO" | sort -u)"
# 1) Tipos de archivo prohibidos
echo "$FILES" | grep -iE '\.(wav|mp3|ogg|opus|flac|m4a|webm|npy|npz|pt|onnx|jsonl|log|sqlite[^/]*|zst)$|(^|/)\.env$|secrets\.env|(^|/)voz\.npz|medidas-voz|(^|/)tmp/|client_secret[^/]*\.json$|oauth-client\.json$|tokens?\.json$' \
  | while read -r f; do [[ -n $f ]] && echo "$f"; done > /tmp/.jarvis-push-$$
[[ -s /tmp/.jarvis-push-$$ ]] && { mal "archivos que no deben subirse:"; sed 's/^/      /' /tmp/.jarvis-push-$$; }
rm -f /tmp/.jarvis-push-$$
# 2) Tamaño
for f in $FILES; do [[ -f $f ]] && (( $(stat -c %s "$f") > 5000000 )) && mal "archivo de más de 5 MB: $f"; done
# 3) Secretos por patrón en lo añadido
DIFF="$(git log -p --format= "$RANGO" | grep '^+' )"
grep -qE '(OPENCLAW_GATEWAY_TOKEN|JARVIS_HUD_TOKEN|SPOTIFY_CLIENT_SECRET|AZURE_SPEECH_KEY|API_KEY|_TOKEN)=[A-Za-z0-9_\-]{12,}' <<<"$DIFF" && mal "asignación de un secreto con valor"
grep -qE '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}|xox[bap]-[A-Za-z0-9-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY)' <<<"$DIFF" && mal "algo con forma de clave (sk-, ghp_, AKIA, clave privada…)"
grep -qE '(GOCSPX-[A-Za-z0-9_-]{20,}|1//0[A-Za-z0-9_-]{30,}|ya29\.[A-Za-z0-9_-]{30,})' <<<"$DIFF" && mal "algo con forma de secreto o token de Google (GOCSPX-, 1//0…, ya29.)"
# 4) Valores reales (sin mostrarlos)
VALS=()
[[ -f ~/.config/jarvis/secrets.env ]] && while IFS='=' read -r k v; do [[ ${#v} -ge 12 ]] && VALS+=("$v"); done < <(grep -E '^[A-Z0-9_]+=' ~/.config/jarvis/secrets.env)
T="$(jq -r '.gateway.auth.token // empty' ~/.openclaw/openclaw.json 2>/dev/null)"; [[ ${#T} -ge 12 ]] && VALS+=("$T")
# D-029: client_secret y refresh tokens de Google (~/.config/jarvis/google)
for f in ~/.config/jarvis/google/*.json; do [[ -f $f ]] || continue
  while IFS= read -r v; do [[ ${#v} -ge 12 ]] && VALS+=("$v"); done < <(jq -r '.. | objects | (.client_secret?, .refresh_token?) // empty' "$f" 2>/dev/null)
done
for v in "${VALS[@]}"; do grep -qF -- "$v" <<<"$DIFF" && mal "un valor REAL de secrets.env o del token del gateway aparece en un commit (${#v} caracteres)"; done
# 5) Transcripciones de voz en texto
# (línea de log: empieza por la etiqueta, o por "run.sh[PID]: "; el código con print("[Usted] …") no cuenta)
grep -qE '^\+[[:space:]]*([A-Za-z]{3} [0-9]{1,2} [0-9:.]+ [a-z0-9-]+ run\.sh\[[0-9]+\]: )?\[(Usted|Jarvis)\] ' <<<"$DIFF" && mal "líneas de transcripción ([Usted]/[Jarvis]) en lo añadido"
((MAL)) && { echo "No se debe hacer push. Corrija y vuelva a revisar."; exit 1; }
echo "  ✔ nada sensible en $N commit(s)."
