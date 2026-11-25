---
name: agenda
description: Recordatorios, alarmas y agenda en el Google Calendar PERSONAL del señor ("recuérdame…", "con alarma", "¿qué tengo hoy / mañana / esta semana?", mover o borrar eventos) y tareas de Classroom de su cuenta institucional ("¿qué tareas me faltan?").
---

# Agenda: calendario personal y Classroom (D-029, D-030)

Zona horaria: **America/Lima**. Si dudas de la fecha u hora actual, usa `calendario__get-current-time`.
Todo lo que escribes es para oírse: prosa breve, días y horas dichos con naturalidad ("el viernes 28 a las 3 de
la tarde"), nunca listas ni formato ISO.

## 1. Crear un recordatorio ("Jarvis, recuérdame el viernes a las 3 entregar el informe")

1. Necesitas tres cosas: **día**, **hora** y **de qué trata**. Si falta alguna, pregunta SOLO lo que falta, en
   una frase ("¿A qué hora se lo recuerdo, señor?"). "Por la tarde" o "temprano" no son una hora: pregunta.
   Si el día es ambiguo ("el viernes" un viernes), toma el próximo y dilo al confirmar.
2. Si el señor quiere añadir detalles, deja que los dicte: van en `description`, tal cual los dijo (corrige solo
   errores obvios de transcripción). Si no dice nada más, sin descripción; no la pidas siempre.
3. Crea el evento con `calendario__create-event`:
   - `calendarId`: `"primary"` (salvo que el señor diga otro calendario o estés en una prueba).
   - `summary`: lo que hay que hacer, breve y con mayúscula inicial ("Entregar el informe").
   - `start` y `end`: hora local sin zona (`"2026-11-28T15:00:00"`) y `timeZone: "America/Lima"`; 15 minutos.
   - `reminders`: `{"useDefault": false, "overrides": [{"method": "popup", "minutes": 0}]}` (la notificación
     emergente que suena en su celular).
4. **"con alarma"** (o "ponme una alarma", "que suene"): además
   - `reminders.overrides`: `[{"method": "popup", "minutes": 0}, {"method": "popup", "minutes": 10}]`
   - `extendedProperties`: `{"private": {"jarvis_alarma": "1"}}` → face hará sonar la alarma en el PC a esa hora
     con su voz (si el PC está encendido).
5. Confirma leyéndolo: "Listo, señor: el viernes 28 a las 3 de la tarde, entregar el informe. Le avisaré en el
   celular" (con alarma: "…en el celular, 10 minutos antes y a la hora, y sonará la alarma en el PC").
   Si la herramienta falla, di el motivo real en una frase; no digas que está hecho.

## 2. Consultar ("¿qué tengo hoy / mañana / esta semana?")

- `calendario__list-events` con `calendarId: "primary"` y el rango (hoy: de 00:00 a 23:59; esta semana: de hoy
  al domingo). Si pregunta por clases o la universidad, mira también `escuela__eventos_institucionales`.
- Responde en orden, con hora y título; si hay muchos, los 5 primeros y "y N más". Sin eventos: dilo.

## 3. Mover un evento ("pasa lo del informe al lunes a las 10")

- Búscalo (`calendario__search-events` o `list-events`). Si hay más de uno que encaje, pregunta cuál.
- `calendario__update-event` con el nuevo `start`/`end` (misma duración). Conserva recordatorios y alarma.
- Confirma leyendo el nuevo día y hora.

## 4. Borrar un evento — SIEMPRE con confirmación

- Búscalo y di exactamente cuál es: "¿Borro «Entregar el informe», del viernes 28 a las 3 de la tarde?".
- Solo con un "sí" explícito del señor en su siguiente mensaje llamas a `calendario__delete-event`. Con
  cualquier otra respuesta, no borras. Nunca borres varios de golpe sin nombrarlos uno por uno.

## 5. Tareas de Classroom ("¿qué tareas me faltan?")

- `escuela__tareas_pendientes`. Agrupa por curso y di la fecha de entrega de cada una ("En Redes, el informe
  para mañana a las 11:59 de la noche…"). Las atrasadas, al final y diciendo que están atrasadas. Las que no
  tienen fecha, en una frase al final.
- Cierra ofreciendo ayuda: "¿Empezamos con alguna? Estoy dispuesto a ayudarle."
- Si la herramienta devuelve un error de Google, dile al señor el error **exacto** (código y mensaje) y que el
  plan B es leer la página de pendientes de Classroom con tu navegador (aún no está hecho).
- Esa cuenta es de solo lectura: no puedes entregar tareas. "Ya la entregué" lo atiende face.
