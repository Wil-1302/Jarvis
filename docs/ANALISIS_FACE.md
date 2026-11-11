# Análisis del código de face (PanPenek/JarvisAi @ 9dcf62b)

Leído el 2026-11-11. Hay unas 4.400 líneas en total; el núcleo son `jarvis/main.py` (443) y `jarvis/tools/router.py` (284).
El historial original tiene solo 3 commits (2026-03-01). Dos de ellos están firmados por `Antigravity <antigravity@openclaw.local>`,
lo que indica que se generaron con una herramienta de IA. `PROJECT_SUMMARY.txt` lo describe como una "versión saneada y vendible"
de un proyecto privado.

## 1. Mapa de módulos

| Archivo | Función |
|---|---|
| `jarvis/main.py` | Orquestador. Contiene el pipeline de voz, el enrutado al LLM, el bucle de tools, abort/mute, el teclado (Esc/F2/Insert), el bus de eventos y el arranque |
| `jarvis/wake.py` | Wake word con openWakeWord sobre PyAudio |
| `jarvis/stt.py` | Grabación hasta silencio (sounddevice) y transcripción (faster-whisper) |
| `jarvis/tts.py` | Kokoro-82M con reproducción frase a frase e interrupción |
| `jarvis/web.py` | FastAPI y WebSocket: HUD, CRUD de proveedores, ajustes y mute |
| `jarvis/static/index.html` | HUD "Iron Man" en un solo archivo HTML, CSS y JS (1.156 líneas) |
| `jarvis/context.py` | Ventana deslizante de mensajes con autoresumen |
| `jarvis/memory.py` | Hechos en ChromaDB y resúmenes en SQLite |
| `jarvis/llm.py` | Llamada simple al LLM sin tools (para resúmenes) |
| `jarvis/tools/*.py` | Las tools (ver §3) |
| `config.yaml` | Toda la configuración. **La UI la reescribe** (`_save_config`) |

Todos los módulos releen `config.yaml` en cada llamada (`_load_config()`). No hay caché, pero eso permite cambiar ajustes en caliente.

## 2. Cómo llama al LLM

Flujo: `handle_wake()`, luego `_handle_wake_inner()` (graba y transcribe), luego **`_process_request(user_text)`** y por último `_call_llm()`.
La entrada por web (WebSocket, mensaje `chat`) y la de teclado (F2) también desembocan en `_process_request`.

`_process_request` (`main.py:350`):
1. Busca hechos relevantes en la memoria (`memory.search_facts`) y los antepone como mensaje `system`.
2. Añade `context.get_messages()` (historial local, con resumen previo) y el mensaje del usuario.
3. Antepone `_system_prompt()`, que está en inglés, es "agéntico", es explícitamente "no refusals, no disclaimers" e incluye la fecha y la hora.
4. Llama a `_call_llm(full_messages)`. **Si falla, reintenta en silencio con Ollama** (`main.py:370`).
5. Guarda el turno en `context`, extrae hechos (por palabras clave en inglés: "my name is", "i like"... e **incluso "my password"**) y emite el evento `response`.

`_call_llm` (`main.py:265`) lee `llm.active_provider` y enruta según `type`:
- **`openai`**: `_call_openai_provider` usa el SDK `openai` con `base_url` y `api_key` tomados de `config.yaml`
  (por defecto `"lm-studio"`). Hay un cliente cacheado por `base_url`, con timeout de 60 s.
  Llama a `chat.completions.create(model, messages, tools=TOOL_SCHEMAS, temperature)` **sin streaming**.
- **Cualquier otro valor**: `_call_ollama_provider` llama a `ollama.chat(...)` con el SDK de Ollama, que siempre usa el host por defecto e ignora `base_url`.

Bucle de tools (los dos proveedores siguen el mismo patrón, `main.py:205`): hasta `_MAX_TOOL_LOOPS = 15` iteraciones.
En cada una:
- Si la respuesta trae `tool_calls`, añade el mensaje del asistente y ejecuta cada tool con `_exec_tool_with_retry`, que reintenta una vez si falla.
- Emite los eventos `tool` y `tool_result` al HUD y añade `{"role":"tool","content":..., "tool_call_id":...}`.
- En la cuarta tool dice "Working on it." en voz alta.
- Sin `tool_calls`, devuelve `msg.content` sin los bloques `<think>`.

Otras llamadas al LLM:
- `jarvis/llm.py::chat()` la usa `context.py` para resumir cuando la ventana llega a `summarize_after` mensajes. Usa el mismo proveedor activo, sin tools, con timeout de 15 s y Ollama como reserva.
- `jarvis/tools/subagent.py::delegate_task` usa **Ollama con `qwen3:8b` fijo en el código**.

## 3. Cómo arma y ejecuta las tools

- `jarvis/tools/router.py` define dos estructuras paralelas:
  - `TOOL_MAP`: nombre → `lambda args: función(...)`.
  - `TOOL_SCHEMAS`: lista en formato OpenAI `{"type":"function","function":{name, description, parameters}}`. Sirve tal cual para OpenAI y para Ollama.
- `dispatch(name, args)` devuelve siempre un `str`. Los errores se convierten en `"Tool 'x' failed: ..."`.
- **Son 32 tools, no 31** como dice el README. `delegate_task` se añadió después.

| Grupo | Tools | Archivo |
|---|---|---|
| Web | `web_search`, `fetch_page`, `open_url`, `get_weather` | `web_search.py`, `app_control.py` |
| Apps | `open_app` (≈30 apps mapeadas), `kill_process` | `app_control.py` |
| Visión / ratón | `read_screen`, `find_on_screen` (OCR con PowerShell), `click_at`, `scroll_screen`, `move_mouse` | `desktop.py` |
| Ventanas / teclado | `focus_window`, `get_open_windows`, `type_text`, `press_key`, `media_control`, `screenshot` | `desktop.py` |
| Archivos | `read_file`, `write_file`, `list_files` (limitados a `tools.allowed_paths`) | `file_ops.py` |
| Código | `run_python` | `code_exec.py` |
| Sistema | `get/set_clipboard`, `set/get_volume`, `get_system_info`, `set_brightness`, `lock_screen`, `power_command` | `system.py` |
| Avisos | `show_notification`, `set_timer` | `system.py` |
| Subagente | `delegate_task` | `subagent.py` |

Riesgos que hay que tener en cuenta:
- **`run_python` no es un sandbox.** Ejecuta el código con el mismo intérprete y los mismos permisos que el usuario; solo tiene un timeout de 10 s.
- **`power_command`, `kill_process`, `write_file` y `type_text`/`press_key` se ejecutan sin confirmación.** El prompt del sistema además pide "no refusals".
- `pyautogui.FAILSAFE = False` (`desktop.py`): no se puede abortar llevando el ratón a una esquina.
- `set_clipboard` interpola texto en PowerShell con un escape mínimo de comillas.

## 4. Dónde están STT, TTS y wake word

**Wake word** (`jarvis/wake.py`):
- `openwakeword.model.Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")` sobre PyAudio a 16 kHz, en chunks de 1.280 muestras. El umbral se define en `config.yaml`.
- Decir la wake word con Jarvis inactivo lanza `callback()` en un hilo. Decirla mientras está ocupado ejecuta `abort_all()`.
- Hay cooldowns de 2 y 3 s para evitar el eco del "Yes?".
- Durante el STT el micrófono se pausa con un `threading.Event` (`pause_wake_mic`/`resume_wake_mic`).
- ⚠️ **Smart App Control**: en JARVIS-WIL bloqueó `_liblinear.pyd` (sklearn), que el paquete `openwakeword` importa.
  Si vuelve a pasar, hay que hacer lo mismo que antes: cargar los ONNX (`melspectrogram`, `embedding`, `hey_jarvis`)
  directamente con onnxruntime y no usar `openwakeword.model`.

**STT** (`jarvis/stt.py`):
- `record_until_silence()` usa `sounddevice` en chunks de 300 ms con detección por RMS: el habla empieza al superar 0,015 y la grabación se corta tras unos 2,1 s por debajo de 0,012. El máximo es de 30 s y se respeta el abort.
- `transcribe_audio()` usa faster-whisper (`small`, `cuda`/`int8`, con reserva automática a CPU) y `beam_size=5`.
- ⚠️ **`language="en"` está fijo en el código** (`stt.py:45` y `stt.py:53`). Para español hay que hacerlo configurable (Fase 4).
- La grabación usa sounddevice y la wake word usa PyAudio: son dos librerías de audio distintas.

**TTS** (`jarvis/tts.py`):
- Kokoro `KPipeline(lang_code="a")`, que es inglés americano **fijo en el código**. Para español hace falta `lang_code="e"` y una voz `ef_*`/`em_*`; para británico, `"b"` con `bm_*`.
- Voz configurable (`tts.voice: af_heart`) a 24 kHz, con `speak_streamed()` que sintetiza y reproduce frase a frase.
- Busca el modelo en `~/Downloads/kokoro-v1_0.pth`, una ruta poco limpia. Las voces las descarga de HF con `local_files_only=True`, que **falla si no están ya en caché**.

**HUD** (`jarvis/web.py` + `static/index.html`):
- FastAPI en el puerto 7860 con WebSocket `/ws`. `main._broadcast()` envía eventos `{type: status|user|tool|tool_result|response|mute|provider_changed}`.
- El HUD ya pinta los estados LISTENING / PROCESSING / SPEAKING del reactor a partir de `status` (`"Listening..."`, `"Thinking..."`, `"Speaking..."`). Eso servirá para la Fase 4.
- Tiene un selector de proveedor que llama a `/api/providers/{key}`. Servirá como base para mostrar el "cerebro activo" en la Fase 5.

## 5. Hallazgos de seguridad en face

1. **`web.py:234` escucha en `host="0.0.0.0"`.** El HUD, la API y el WebSocket (que ejecuta tools) quedan accesibles desde la red local **sin autenticación**. Hay que cambiarlo a `127.0.0.1`.
2. **`GET /api/providers` devuelve `api_key` en claro**, y `PUT` la guarda en `config.yaml`. Con OpenClaw, el token del gateway **no puede vivir en `config.yaml`**: debe leerse de `.env`, y la API no debe devolverlo.
3. `_save_config()` reescribe `config.yaml` entero con `yaml.dump`, lo que borra los comentarios. Cualquier secreto que se ponga ahí acaba en disco y quizá en git.
4. La memoria guarda frases con "my password" como hechos en ChromaDB.
5. El fallback silencioso a Ollama oculta los fallos del proveedor activo y además cambia de modelo sin avisar.

## 6. Qué cambiar para usar OpenClaw como proveedor (Fase 3)

El punto de entrada natural es `type: openai`: OpenClaw expone `POST /v1/chat/completions`, compatible con el SDK `openai`.
Esto está verificado en `brain/openclaw/docs/gateway/openai-http-api.md`:
- `model` es un **agente**, no un modelo: `openclaw/default`, `openclaw/<agentId>` u `openclaw:<agentId>`. `GET /v1/models` lista los agentes.
- `x-openclaw-model: <proveedor/modelo>` cambia el modelo por petición. Con un bearer de secreto compartido no requiere scopes extra.
- `user` estable → OpenClaw deriva una clave de sesión estable, así que **la sesión y el historial viven en OpenClaw**.
- El endpoint acepta `tools` (subconjunto función) y `tool_choice`, y devuelve `tool_calls` con el formato OpenAI estándar.
  El cliente ejecuta la tool y reenvía los mensajes `role: "tool"`. Esto hace viable la opción (B) de CLAUDE.md.
- Se activa con `gateway.http.endpoints.chatCompletions.enabled: true`. Auth: `Authorization: Bearer <token>`
  (`gateway.auth.token` u `OPENCLAW_GATEWAY_TOKEN`). La documentación insiste en que el token equivale a una credencial de operador
  y en que el endpoint solo debe estar en loopback o en una red privada.

Archivos a tocar:

| Archivo | Cambio |
|---|---|
| `face/config.yaml` | Nuevo proveedor `openclaw: {type: openclaw, base_url: http://127.0.0.1:18789/v1, model: openclaw/jarvis, api_key_env: OPENCLAW_GATEWAY_TOKEN, user_env: OPENCLAW_SESSION_USER, send_tools: false\|true}` **sin el token** |
| `face/jarvis/main.py` | `_call_llm`: nuevo tipo `openclaw` (o una extensión de `_call_openai_provider`) que (a) lea el token de `.env`, (b) envíe `user=` estable y `extra_headers={"x-openclaw-model": ...}` (Fase 5), (c) envíe `tools=TOOL_SCHEMAS` solo en la opción B, (d) mande **solo el mensaje nuevo** (u omita el historial local), porque OpenClaw ya guarda la sesión. También: subir el timeout (los agentes tardan más de 60 s con tools) y quitar o hacer explícito el fallback a Ollama |
| `face/jarvis/context.py` / `llm.py` | En modo OpenClaw, desactivar el resumen local, o enviarlo a Ollama local y no al gateway, para no ensuciar la sesión del agente |
| `face/jarvis/memory.py` | En modo OpenClaw la memoria es de OpenClaw: desactivar la extracción y búsqueda local de hechos, o dejarla opcional |
| `face/jarvis/tools/subagent.py` | Quitar el `qwen3:8b` fijo o retirar la tool en modo OpenClaw (los subagentes los gestiona OpenClaw) |
| `face/jarvis/tools/router.py` | Opción B: exponer un subconjunto seguro de `TOOL_SCHEMAS` y marcar qué tools requieren confirmación |
| `face/jarvis/web.py` | `host=127.0.0.1`; no devolver `api_key`; endpoint o evento con el "cerebro activo" |
| `face/jarvis/static/index.html` | Mostrar el agente y el modelo activos (Fase 5) |
| `face/requirements.txt` | Añadir `python-dotenv` para leer `.env` (o leer `os.environ`) |
| `face/jarvis/stt.py`, `tts.py` | Idioma y voz configurables (Fase 4; no es parte del puente, pero hay que tocarlos) |
| `face/jarvis/wake.py` | Solo si Smart App Control vuelve a bloquear sklearn |

**Decisión pendiente (Fase 3)**: las opciones (A) y (B) se prueban ahí. Adelanto que (B) encaja bien con el endpoint,
porque el ciclo `tool_calls` → `role: tool` es justo el que ya implementa `_call_openai_provider`.
Pero solo debería exponerse un subconjunto de tools, con confirmación para `power_command`, `kill_process`, `write_file` y `run_python`.
