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
SECRETS="${JARVIS_SECRETS:-$HOME/.config/jarvis/secrets.env}"
chk "secretos de face en ~/.config/jarvis/secrets.env (600, carpeta 700)" bash -c "[[ \$(stat -c %a '$SECRETS') == 600 && \$(stat -c %a '$(dirname "$SECRETS")') == 700 ]] && grep -q '^OPENCLAW_GATEWAY_TOKEN=.\{32,\}' '$SECRETS'"
chk "sin .env antiguo en el repo" test ! -e "$REPO/.env"
TOKEN="$(grep -m1 '^OPENCLAW_GATEWAY_TOKEN=' "$SECRETS" 2>/dev/null | cut -d= -f2-)"
chk "/v1/models lista openclaw/jarvis" bash -c "curl -sf -H 'Authorization: Bearer $TOKEN' http://127.0.0.1:18789/v1/models | grep -q openclaw/jarvis"
chk "sin token → 401" bash -c "[[ \$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18789/v1/models) == 401 ]]"
chk "principal de face = principal del agente jarvis (estricto)" bash -c "[[ \$(jq -r .agents.entries.jarvis.model.primary ~/.openclaw/openclaw.json) == \$(grep -m1 'primary_model:' '$REPO/face/config.yaml' | awk '{print \$2}') ]]"
BACKUP="$(grep -m1 'backup_model:' "$REPO/face/config.yaml" | awk '{print $2}')"
chk "respaldo $BACKUP responde (login de ChatGPT/Codex)" bash -c "curl -sf -m 90 -H 'Authorization: Bearer $TOKEN' -H 'x-openclaw-model: $BACKUP' -H 'Content-Type: application/json' http://127.0.0.1:18789/v1/chat/completions -d '{\"model\":\"openclaw/jarvis\",\"user\":\"doctor\",\"messages\":[{\"role\":\"user\",\"content\":\"Responde solo: ok\"}]}' | grep -q choices"
echo "Refuerzos (D-013)"
chk "e) ni systemctl/systemd-run/loginctl/crontab/at/busctl/intérpretes en la allowlist; ask=on-miss, sin aprobar → denegar" bash -c "openclaw approvals get --json 2>/dev/null | python3 -c '
import json,sys,re
d=json.load(sys.stdin)[\"file\"]; malo=re.compile(r\"(^|/)(systemctl|systemd-run|loginctl|crontab|at|batch|busctl|gdbus|dbus-send|sudo|doas|pkexec|sh|bash|fish|zsh|python3?|node|perl|ruby|env|openclaw|sqlite3)\$\")
for n,a in [(\"defaults\",d[\"defaults\"])]+list(d.get(\"agents\",{}).items()):
    assert a.get(\"askFallback\",\"deny\")==\"deny\" and a.get(\"security\")!=\"full\" and not a.get(\"autoAllowSkills\"), n
    for e in a.get(\"allowlist\",[]): assert not malo.search(e[\"pattern\"]), e[\"pattern\"]
'"
P=$(systemctl --user show openclaw-gateway -p MainPID --value)
chk "a) el gateway no puede leer ~/.config/jarvis" bash -c "! nsenter -t $P -U -m --preserve-credentials -- cat '$SECRETS' >/dev/null 2>&1"
chk "b) el gateway no puede escribir unidades, atajos, shells, ~/.local/bin ni el repo" bash -c "for f in ~/.config/systemd/user/.p ~/.config/caelestia/.p ~/.config/fish/.p ~/.local/bin/.p '$REPO/.p'; do nsenter -t $P -U -m --preserve-credentials -- touch \$f 2>/dev/null && { rm -f \$f; exit 1; }; done; true"
chk "c) workspace propio del agente jarvis" bash -c "openclaw config get agents.entries.jarvis.workspace 2>/dev/null | grep -q workspace-jarvis"
chk "d) el gateway no puede reescribir openclaw.json, AGENTS.md ni skills" bash -c "for f in ~/.openclaw/openclaw.json ~/.openclaw/workspace-jarvis/AGENTS.md; do nsenter -t $P -U -m --preserve-credentials -- sh -c \"echo >> \$f\" 2>/dev/null && exit 1; done; ! nsenter -t $P -U -m --preserve-credentials -- touch ~/.openclaw/workspace-jarvis/skills/.p 2>/dev/null"
echo "Cara (face)"
chk "venv de face" test -x "$REPO/face/.venv/bin/python"
chk "jarvis-face activo" systemctl --user is-active jarvis-face.service
chk "HUD solo en loopback" bash -c "ss -tlnH 'sport = :7860' | awk '{print \$4}' | grep -q '^127.0.0.1:' && ! ss -tlnH 'sport = :7860' | awk '{print \$4}' | grep -qE '^(0\.0\.0\.0|\*|\[::\]):'"
chk "HUD sin token → 401" bash -c "[[ \$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:7860/api/providers) == 401 ]]"
if r=$("$REPO/scripts/bin/jarvis-mic-actual" 2>&1); then ok "micrófono de face: ${r#face graba de: }"; else ko "micrófono de face: $r"; fi
chk "ydotool activo (música por la app de escritorio, D-018)" systemctl --user is-active ydotool.service
echo "Arranque con la sesión gráfica (no con linger: sin entorno de Hyprland ni /dev/uinput)"
for u in jarvis-face ydotool; do
  chk "$u arranca con graphical-session.target, no con default.target" bash -c "w=\$(systemctl --user show $u -p WantedBy --value); [[ \$w == *graphical-session.target* && \$w != *default.target* ]] && systemctl --user show $u -p After --value | grep -q graphical-session.target"
done
FP=$(systemctl --user show jarvis-face -p MainPID --value)
chk "face ve a Hyprland (WAYLAND_DISPLAY e HYPRLAND_INSTANCE_SIGNATURE vigentes)" bash -c "e=\$(tr '\\0' '\\n' < /proc/$FP/environ); s=\$(grep -m1 '^HYPRLAND_INSTANCE_SIGNATURE=' <<<\"\$e\" | cut -d= -f2-); w=\$(grep -m1 '^WAYLAND_DISPLAY=' <<<\"\$e\" | cut -d= -f2-); [[ -n \$s && -S \$XDG_RUNTIME_DIR/hypr/\$s/.socket.sock && -n \$w && -S \$XDG_RUNTIME_DIR/\$w ]]"
chk "el usuario puede escribir en /dev/uinput (ACL de logind)" test -w /dev/uinput
chk "ydotoold sin errores de permiso desde su último arranque" bash -c "! journalctl --user -u ydotool --since \"\$(systemctl --user show ydotool -p ActiveEnterTimestamp --value)\" --no-pager -q | grep -q 'Permission denied'"
echo "Navegador de JARVIS (D-026)"
chk "browser: perfil propio, sin evaluate" bash -c "openclaw config get browser --json 2>/dev/null | python -c 'import json,sys; b=json.load(sys.stdin); assert b[\"enabled\"] and b[\"evaluateEnabled\"] is False and b[\"executablePath\"].endswith(\"/scripts/bin/jarvis-chrome\") and b[\"defaultProfile\"]==\"jarvis\" and b.get(\"ssrfPolicy\")=={}'"
chk "jarvis-chrome rechaza el Chrome personal" bash -c "! \"$REPO/scripts/bin/jarvis-chrome\" --headless --user-data-dir=\"\$HOME/.config/google-chrome\" 2>/dev/null"
echo "Google: calendario personal y Classroom (D-029)"
G="$HOME/.config/jarvis/google"
chk "credenciales en $G (carpeta 700, archivos 600)" bash -c "[[ \$(stat -c %a '$G') == 700 ]] && for f in '$G'/*.json; do [[ \$(stat -c %a \"\$f\") == 600 ]] || exit 1; done && test -f '$G/oauth-client.json'"
chk "el gateway no puede leer los tokens de Google" bash -c "! nsenter -t $P -U -m --preserve-credentials -- ls '$G' >/dev/null 2>&1"
for s in "jarvis-calendario 18820" "jarvis-escuela 18821"; do set -- $s
  chk "$1 activo y solo en 127.0.0.1:$2" bash -c "systemctl --user is-active -q $1 && ss -tlnH 'sport = :$2' | awk '{print \$4}' | grep -q '^127.0.0.1:' && ! ss -tlnH 'sport = :$2' | awk '{print \$4}' | grep -qE '^(0\.0\.0\.0|\*|\[::\]):'"
done
chk "calendario fijado en 2.8.1" bash -c "[[ \$(node -p \"require('$HOME/.local/lib/jarvis-mcp/google-calendar/node_modules/@cocal/google-calendar-mcp/package.json').version\") == 2.8.1 ]]"
chk "OpenClaw: calendario y escuela por HTTP local; main sin acceso" bash -c "jq -e '(.mcp.servers.calendario.url == \"http://127.0.0.1:18820/mcp\") and (.mcp.servers.escuela.url == \"http://127.0.0.1:18821/mcp\") and ((.mcp.servers.calendario.toolFilter.include | index(\"manage-accounts\")) == null) and ((.agents.entries.main.tools.deny | index(\"calendario__*\")) != null)' ~/.openclaw/openclaw.json"
GC=$("$REPO/scripts/jarvis-google" check 2>&1)
if grep -qE '^(personal|escuela)' <<<"$GC"; then
  while IFS= read -r l; do case $l in *": OK"*|*": "*" OK"*) ok "token $l";; *) ko "token $l";; esac; done < <(grep -E '^(personal|escuela)' <<<"$GC" | sed 's/  */ /g')
else ko "tokens de Google: $(head -1 <<<"$GC")"; fi
echo "Sistema"
chk "sin Ollama/CUDA (D-008)" bash -c "! pacman -Q ollama >/dev/null 2>&1 && ! pacman -Q cuda >/dev/null 2>&1"
chk "ufw activo" systemctl is-active ufw.service
chk "linger" bash -c "loginctl show-user $USER -p Linger | grep -q yes"
chk "GPU NVIDIA visible" nvidia-smi -L
echo; ((FALLOS==0)) && echo "Todo en verde." || echo "$FALLOS comprobación(es) en rojo."
exit $((FALLOS>0))
