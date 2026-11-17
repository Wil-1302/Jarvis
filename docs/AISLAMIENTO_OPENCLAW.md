# Aislamiento de OpenClaw frente a rutas sensibles

Fecha: 2026-11-17 · Bloque 5 · Fuente: docs del submodule `brain/openclaw` (commit del 2026-11-11) y pruebas locales.

## Problema

El gateway corre como servicio systemd **de mi usuario** (`wil`). Todo lo que lance (exec, skills, servidores MCP)
tiene, por defecto, los mismos permisos que yo: puede leer `~/.ssh/id_ed25519`, las cookies de los navegadores,
`~/.gnupg` o `~/CyberLab`. Un prompt injection (una web, un correo, un documento) podría pedirle al agente que lo haga.

Rutas a proteger (existen hoy en la máquina, salvo las marcadas):

| Ruta | Motivo |
| --- | --- |
| `~/.ssh` | llave de GitHub |
| `~/.gnupg`, `~/.local/share/keyrings` | llaves GPG, llavero de GNOME (contraseñas guardadas) |
| `~/.config/{google-chrome,chromium,BraveSoftware,vivaldi,microsoft-edge,opera}`, `~/.mozilla` (no existe) | cookies y contraseñas de navegadores |
| `~/CyberLab` | laboratorio de seguridad |
| `~/.aws`, `~/.config/gh`, `~/.claude`, `~/.git-credentials`, `~/.netrc`, `~/.docker`, `~/.kube` | credenciales de otras herramientas (algunas no existen; se bloquean igual con `-`) |

## Qué ofrece OpenClaw (según su doc)

1. **Herramientas de archivos** (`read`/`write`/`edit`/`apply_patch`): se pueden confinar al workspace del agente con
   `tools.fs.workspaceOnly: true` y `tools.exec.applyPatch.workspaceOnly: true` (este último ya es el valor por
   defecto), o con el modo de permisos de sesión `guarded` ("Ask me"): lecturas y escrituras solo bajo `sessionRoot`.
   El workspace debe ser una carpeta propia (no `$HOME`), p. ej. `~/.openclaw/workspace-jarvis`.
2. **`exec` en el host**: **no hay lista de rutas prohibidas.** La doc lo dice explícitamente: la política de tools
   filtra por nombre y "no inspecciona los efectos de `exec`" (`docs/gateway/sandbox-vs-tool-policy-vs-elevated.md`),
   y fs-safe "es una barrera de librería, no un sandbox" (`docs/gateway/security/secure-file-operations.md`).
   Lo único es el control por comando: aprobaciones de exec con `security: "allowlist"`, `ask: "on-miss"`,
   `askFallback: "deny"` (lo que no está en la lista pide aprobación humana en la Control UI; un "sí" escrito no vale).
3. **Sandbox** (Docker/Podman): exec corre en un contenedor que solo ve el workspace y los `binds` que se den; OpenClaw
   además rechaza binds de `~/.ssh`, `~/.gnupg`, `~/.config`, `~/.aws`… Es aislamiento real, pero dentro del contenedor
   no hay bus de sesión, PipeWire ni Wayland: las acciones de escritorio (música, volumen, notificaciones, ydotool)
   tendrían que salir por MCP/tools fuera del sandbox.
4. Para aislamiento fuerte la doc recomienda **usuarios del sistema separados** o sandbox.

## Qué se probó en esta máquina (systemd 262, userns sin privilegios activo)

Unidad transitoria de usuario con `InaccessiblePaths=`:

- `ls ~/.ssh`, `ls ~/CyberLab` → **Permiso denegado**; `touch ~/.ssh/x` → **denegado**.
- `~/Proyectos` legible y `playerctl -l` ve Spotify → el escritorio sigue funcionando.
- **Evasión confirmada:** desde dentro, `systemd-run --user ls ~/.ssh` **lista la carpeta**: el gestor systemd del
  usuario (vía el bus de sesión) lanza el proceso fuera del encierro. Lo mismo valdría para `systemctl --user`,
  `busctl`/`gdbus`/`dbus-send` hacia `org.freedesktop.systemd1`, o `ydotool` escribiendo en una terminal abierta.
- Quitar `AF_UNIX` cierra esa vía pero rompe el bus de sesión (playerctl falla) → no sirve para JARVIS.

## Propuesta (defensa en capas)

**Capa 1 — configuración de OpenClaw** (en `brain/config/`, se aplica en el onboarding):

```json5
{
  agents: { entries: { jarvis: {
    workspace: "~/.openclaw/workspace-jarvis",
    newSessionPermissionMode: "guarded",
  } } },
  tools: {
    fs: { workspaceOnly: true },
    exec: { applyPatch: { workspaceOnly: true } },
    elevated: { enabled: false },
  },
}
// exec approvals: security "allowlist", ask "on-miss", askFallback "deny";
// allowlist corta (playerctl, wpctl, notify-send, brightnessctl…) con argPattern cuando aplique.
// NUNCA en la allowlist: intérpretes (bash, sh, python, node), systemd-run, systemctl, busctl,
// gdbus, dbus-send, ydotool, cat/cp/tar/curl sin argPattern.
```

Claves a verificar contra el esquema real con `openclaw config validate` / `openclaw sandbox explain` al instalar.

**Capa 2 — encierro del servicio** (`scripts/systemd/openclaw-gateway.service.d/jarvis-aislamiento.conf`,
lo instala `sync-brain.sh` en `~/.config/systemd/user/openclaw-gateway.service.d/`): `InaccessiblePaths=` sobre las
rutas de la tabla, más `NoNewPrivileges=yes`. Cubre al gateway **y a todos sus hijos** (exec, MCP stdio, skills) aunque
la capa 1 falle o se configure mal. No necesita sudo.

**Capa 3 — cerrar la evasión por el bus:** la capa 1 ya obliga a aprobar a mano cualquier `systemd-run`,
`systemctl`, `busctl`, intérprete o `ydotool`. Opcional más adelante: `xdg-dbus-proxy` delante del bus de sesión con
solo los nombres MPRIS/notificaciones permitidos (más complejo; se evalúa en el Bloque 9).

**Riesgo residual (aceptado si se elige esta opción):** un comando aprobado por error puede evadir la capa 2, y lo
que el agente vea en pantalla o en el portapapeles no está protegido. Por eso las aprobaciones nunca se dan por voz.

## Alternativas más fuertes (⏸ decisión del usuario, ver D-007)

| Opción | Aislamiento | Coste |
| --- | --- | --- |
| A. Capas 1+2+3 con mi usuario (recomendada ahora) | bueno contra lecturas directas; evadible con un comando aprobado | nulo; todo el escritorio funciona |
| B. Sandbox Podman rootless para exec (`agents.defaults.sandbox.mode: "all"`, `workspaceAccess: "rw"`) | real para exec; las tools de escritorio salen por MCP fuera del sandbox | instalar `podman` (sudo); MCP de escritorio fuera del sandbox siguen con mi usuario |
| C. Usuario del sistema `jarvis` separado (`$HOME` de `wil` ya es 700) | el más fuerte: el kernel impide leer `/home/wil` | sin acceso a mi bus de sesión, PipeWire, Wayland ni Spotify; habría que exponerle un puente estrecho (MCP propio con allowlist) corriendo con mi usuario; más mantenimiento |

Recomendación: **A ahora** (sin sudo, no rompe nada) y **B** cuando se instalen los MCP del Bloque 9, si el señor
quiere exec realmente aislado. C solo si JARVIS llega a recibir contenido de terceros a diario (correo, web) sin
supervisión.
