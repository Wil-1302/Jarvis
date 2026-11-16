# scripts

Scripts bash idempotentes que muestran lo que van a hacer antes de hacerlo:
`sync-brain.sh`, `start-all.sh`, `stop-all.sh`, `doctor.sh` (solo lectura).

- `arch/`: scripts que necesitan root. **Los ejecuta el usuario** (`sudo bash scripts/arch/<script>.sh`).
- `systemd/`: unidades de usuario (`jarvis-face.service`).
