---
name: documento
description: Escribir un documento de Word (.docx) y abrirlo en LibreOffice cuando el señor pide "escríbeme un documento / una receta / una carta / un informe sobre X".
metadata: { "openclaw": { "requires": { "bins": ["soffice", "hyprctl"] } } }
---

# Documento .docx

1. Redacta el contenido completo en español, bien estructurado, como **HTML simple**:
   `<h1>` título, `<h2>` secciones, `<p>`, `<ul>/<ol>/<li>`, `<b>`, `<i>`, `<table>` si hace falta.
   Incluye `<meta charset="utf-8">`. Sin CSS externo, sin imágenes, sin scripts.
   Para una receta: título, raciones y tiempo, ingredientes (lista), preparación (pasos numerados), consejos.
2. Guarda el HTML en el workspace con la herramienta de escritura, p. ej. `documentos/receta-tortilla.html`.
3. Ejecuta: `~/Proyectos/Jarvis/scripts/bin/jarvis-documento documentos/<archivo>.html "<Nombre legible>"`
   (nombre: letras, números, espacios, `_` y `-`; máximo 60 caracteres).
4. Contesta en una o dos frases: qué documento creaste y que ya está abierto en Writer. No leas el documento
   entero en voz alta salvo que el señor lo pida.
