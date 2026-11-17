---
name: abrir-aplicacion
description: Abrir una aplicación del escritorio cuando el señor dice "abre X", "lanza X" o "pon X" (Spotify, Chrome, terminal, archivos, Writer, Steam...).
metadata: { "openclaw": { "requires": { "bins": ["hyprctl", "gtk-launch"] } } }
---

# Abrir aplicación

1. Extrae el nombre de la aplicación tal como lo dijo el señor (corrige errores obvios de transcripción:
   "espotifai" → "spotify", "crom" → "chrome").
2. Ejecuta exactamente: `~/Proyectos/Jarvis/scripts/bin/jarvis-abrir "<nombre>"`
   (un solo argumento entre comillas; solo letras, números, espacios, `.`, `+`, `-`).
3. Si responde "Abierta: …", contesta en una frase: "Listo, señor, he abierto <app>."
   Si no la encuentra, dilo y pregunta por el nombre exacto. No pruebes otros comandos para lanzarla.
