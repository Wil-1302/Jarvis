# Google: calendario personal y Classroom (D-029)

| Servidor | Cuenta | Qué es | Puerto | Permisos de Google |
|---|---|---|---|---|
| `calendario` | personal (la del celular) | [nspady/google-calendar-mcp](https://github.com/nspady/google-calendar-mcp) **2.8.1** (npm `@cocal/google-calendar-mcp`, lockfile en `mcp/calendario/`) | 127.0.0.1:18820 | `calendar` (lectura y escritura) |
| `escuela` | institucional | `mcp/escuela/servidor.py` (nuestro, solo biblioteca estándar) | 127.0.0.1:18821 | `classroom.courses.readonly`, `classroom.coursework.me.readonly`, `classroom.student-submissions.me.readonly`, `calendar.readonly` |

- Los dos son servicios de usuario (`jarvis-calendario`, `jarvis-escuela`) **fuera del encierro del gateway**. El
  cliente OAuth y los tokens viven en `~/.config/jarvis/google/` (700, archivos 600), que el gateway no puede leer:
  el agente solo llega a Google por las herramientas MCP. Cada servicio, además, no ve el token del otro.
- Herramientas expuestas (filtradas dos veces: en el servidor y en `toolFilter` de OpenClaw):
  - calendario: `list-calendars`, `list-events`, `search-events`, `get-event`, `create-event`, `update-event`,
    `delete-event`, `get-freebusy`, `get-current-time`. Fuera: `manage-accounts`, `respond-to-event`, `create-events`.
  - escuela: `tareas_pendientes`, `cursos`, `eventos_institucionales`.
- Revisión de nspady 2.8.1 (24/11/2026): sin scripts de instalación; solo habla con `googleapis.com` y
  `accounts.google.com`; sin `child_process`, `eval` ni telemetría; tokens con 0600. `npm audit`: 5 moderadas en
  glob/minimatch/rimraf (dependencias de googleapis-common, no reciben datos de red). Su HTTP **no tiene
  autenticación** (valida Origin): cualquier proceso local podría usarlo. El agente no: `curl` pide aprobación y el
  navegador tiene 127.0.0.1 bloqueado (ssrfPolicy).

## Instalación

```bash
scripts/install-google.sh            # idempotente: paquete fijado (npm ci --ignore-scripts), unidades, servicios
scripts/jarvis-google login personal # ⏸ el señor
scripts/jarvis-google login escuela  # ⏸ el señor
scripts/sync-brain.sh                # config de OpenClaw (mcp.servers) + skill agenda
scripts/jarvis-google check          # ¿siguen valiendo los tokens? (también en doctor.sh)
```

## Proyecto de Google Cloud (una vez, con la cuenta personal)

1. <https://console.cloud.google.com/projectcreate> → nombre `jarvis-personal` → Crear. Selecciónelo arriba.
2. APIs: abra y pulse **Habilitar** en
   <https://console.cloud.google.com/apis/library/calendar-json.googleapis.com> y
   <https://console.cloud.google.com/apis/library/classroom.googleapis.com>.
3. Pantalla de consentimiento: <https://console.cloud.google.com/auth/overview> → **Comenzar**.
   - Información de la app: nombre `JARVIS`, correo de asistencia = su correo personal → Siguiente.
   - Público: **Externo** → Siguiente. Contacto: su correo personal → Siguiente → acepte la política → Crear.
4. Usuarios de prueba: **Público** (`/auth/audience`) → *Usuarios de prueba* → **Add users** → sus dos correos
   (personal e institucional) → Guardar.
5. Permisos (opcional, pero queda documentado): **Acceso a los datos** (`/auth/scopes`) → *Agregar o quitar
   permisos* → pegue en «Agregar permisos manualmente»:
   `https://www.googleapis.com/auth/calendar`, `https://www.googleapis.com/auth/calendar.readonly`,
   `https://www.googleapis.com/auth/classroom.courses.readonly`,
   `https://www.googleapis.com/auth/classroom.coursework.me.readonly`,
   `https://www.googleapis.com/auth/classroom.student-submissions.me.readonly` → Agregar a la tabla → Actualizar → Guardar.
6. Cliente: **Clientes** (`/auth/clients`) → **Crear cliente** → Tipo **App de escritorio** → nombre `jarvis-pc` →
   Crear → **Descargar JSON**. Luego, en una terminal:
   ```bash
   install -m 600 ~/Descargas/client_secret_*.json ~/.config/jarvis/google/oauth-client.json && rm ~/Descargas/client_secret_*.json
   ```
   El JSON nunca va al repo (`.gitignore` y el hook pre-push lo vigilan).

### Pasarla a producción sin verificación (para que el login no caduque a los 7 días)

En modo **Prueba**, Google invalida el refresh token a los 7 días. En **Producción** no caduca (salvo que cambie
la contraseña, revoque el acceso o pasen 6 meses sin usarlo).

- **Público** → *Estado de publicación: Prueba* → **Publicar app** → Confirmar.
- Google avisará de que la app pide permisos sensibles (Calendar, Classroom) y «necesita verificación». **No envíe
  la verificación**: una app sin verificar funciona igual para hasta 100 usuarios; la única diferencia es una
  pantalla «Google no ha verificado esta app» al iniciar sesión → *Configuración avanzada* → *Ir a JARVIS (no
  seguro)*. Es su propia app, en su propio proyecto.
- Si ya había iniciado sesión en modo Prueba, repita `scripts/jarvis-google login …` tras publicar (el token
  viejo caduca igualmente a los 7 días).

## Cuenta institucional: si la institución bloquea el acceso

Errores posibles y lo que significan (el script y la herramienta los muestran tal cual):
- En el navegador, `Error 400: admin_policy_enforced` o «<institución> no le ha dado acceso a esta app»: el
  administrador de Google Workspace bloquea apps de terceros no aprobadas.
- `HTTP 403 PERMISSION_DENIED … @ClassroomApiDisabled`: la institución tiene apagado el acceso a la API de Classroom.
- `HTTP 403 … has not been used in project … or it is disabled`: falta habilitar la API en el proyecto (paso 2).

Plan B (pendiente): leer la página de pendientes de Classroom (`https://classroom.google.com/a/not-turned-in/all`)
con el navegador propio de JARVIS (D-026), con la sesión iniciada por el señor en `scripts/jarvis-navegador`.
