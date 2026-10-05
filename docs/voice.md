# JARVIS-WIL — Motor de voz (Fase 2)

Todo el procesamiento de voz es **local**: ningún audio sale del equipo. La única
comunicación de red ocurre al descargar los modelos por primera vez.

## Flujo

```
Micrófono (16 kHz, bloques de 80 ms)
   │
   ├─► openWakeWord "hey_jarvis" (ONNX, CPU) ──────────────┐  wake acústico
   └─► Silero VAD (ONNX, CPU) → frase completa             │
                    │                                       ▼
                    └─► faster-whisper large-v3-turbo (GPU) → ¿"Jarvis" al inicio?
                                                            │
                                ┌───────────────────────────┘
                                ▼
         solo "Jarvis" → responde "¿Sí?" y escucha la orden (LISTENING)
         "Jarvis, <orden>" → THINKING: Ollama qwen3:4b-instruct (streaming)
                                ▼
         Piper es_MX-ald-medium (CPU), frase a frase → altavoces
                                ▼
         anti-eco: micrófono silenciado mientras habla + 400 ms + descarte del búfer
```

Estados (`app/voice/state.py`): `IDLE → WAKE_DETECTED → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE`.

## Componentes instalados

| Componente | Paquete / modelo | Versión | Dónde corre |
|---|---|---|---|
| Captura / reproducción | `sounddevice` (PortAudio), `numpy` | 0.5.6 / 2.5.3 | CPU, host API MME |
| Wake word | modelos ONNX de openWakeWord (`melspectrogram`, `embedding_model`, `hey_jarvis_v0.1`) ejecutados con `onnxruntime` | release v0.5.1 / ORT 1.30.0 | CPU (1,4 ms por bloque de 80 ms) |
| VAD | Silero VAD v6 (`silero_vad_v6.onnx`, incluido en faster-whisper) | — | CPU (0,3 ms por bloque) |
| STT | `faster-whisper` + `ctranslate2`, modelo **`large-v3-turbo`** int8_float16 | 1.2.1 / 4.8.2 | GPU (CUDA 12 vía `nvidia-cublas-cu12` 12.9, `nvidia-cudnn-cu12` 9.27) |
| LLM | Ollama `qwen3:4b-instruct` (streaming) | Ollama 0.34.2 | GPU |
| TTS | `piper-tts`, voz **`es_MX-ald-medium`** (masculina, 22 050 Hz) | 1.8.0 | CPU |

No se usa el paquete `openwakeword` (ver Smart App Control) ni `torch` (Silero va en ONNX).

### Modelos descargados (`models/`, fuera de git)

| Modelo | Tamaño | Uso |
|---|---|---|
| `openwakeword/*.onnx` | 4 MB | wake word |
| `piper/es_MX-ald-medium` | 60 MB | voz de JARVIS |
| `piper/es_MX-claude-high` | 60 MB | voz alternativa (femenina); también genera audio de pruebas |
| `piper/en_US-lessac-medium` | 60 MB | solo para el test que valida el detector con pronunciación inglesa |
| `whisper/large-v3-turbo` | 1,5 GB | STT elegido |
| `whisper/medium`, `whisper/small` | 1,5 GB + 0,5 GB | solo del benchmark; **se pueden borrar** |

`python -m app.voice --download-models` descarga lo necesario según la configuración.

## Elección del modelo Whisper

`scripts/benchmark_stt.py`: 16 frases en español generadas con dos voces Piper + ruido
(SNR 20 dB), con `qwen3:4b-instruct` cargado a la vez en la GPU.

| Modelo | VRAM extra | WER | Latencia media | Máx |
|---|---|---|---|---|
| small | 449 MiB | 31,0 % | 0,15 s | 0,23 s |
| medium | 1028 MiB | 22,9 % | 0,34 s | 0,86 s |
| **large-v3-turbo** | 1162 MiB | **22,1 %** | **0,30 s** | 0,31 s |

- Se elige **large-v3-turbo**: el más preciso y más rápido que medium (decoder de 4 capas).
- El WER está inflado: Whisper escribe "70%" y "8" (cuenta como error frente a "setenta por
  ciento") y la voz sintética `ald` pronuncia mal palabras inglesas como "Spotify".
  Con voz real se espera bastante mejor precisión.
- `large-v3` completo no se probó: ~3 GB en int8_float16, no cabe junto a Ollama en 6 GB.
- `stt_prompt` ("Jarvis, Spotify, YouTube, Chrome.") ayuda a reconocer esos nombres:
  "Harvies, abre spotify…" pasa a "Jarvis, abre Spotify…".
- Con silencio o ruido Whisper alucina ("Gracias por ver el video."): se filtran esas
  frases y las de `no_speech_prob > 0.8` (`app/voice/stt.py`).

## Wake word "Jarvis" en español

El modelo preentrenado `hey_jarvis` de openWakeWord se entrenó con pronunciación inglesa:

| Audio (Piper) | Score máx. |
|---|---|
| "Hey Jarvis" (voz inglesa) | 0,997 |
| "Jarvis" (voz inglesa) | 0,918 |
| "Hello, how are you?" / "Hey Marvin" (inglés) | 0,000 |
| "Jarvis" (voces en español) | 0,03 – 0,20 |
| frases sin Jarvis (español) | 0,00 – 0,21 |

Por eso el modo por defecto es **`hybrid`**:

1. **Acústico** (openWakeWord): instantáneo si se dice "Yárvis" a la inglesa.
2. **Transcripción**: cada frase que recorta el VAD se transcribe con Whisper y se busca
   "jarvis" o variantes (`yarvis`, `harvis`, `jarbis`…, configurable en `wake_aliases`)
   entre las 4 primeras palabras. Funciona con cualquier pronunciación y permite decir
   "Jarvis, ¿cómo estás?" sin pausa.

Coste del modo transcripción: Whisper se ejecuta con cada frase que se oye en la
habitación (~0,3 s de GPU por frase). Lo transcrito sin "Jarvis" se descarta: no se
guarda en el log ni en disco.

Otros modos (`JARVIS_WAKE_ENGINE`): `acoustic` (solo openWakeWord) y `transcript` (solo Whisper).

Mejora futura: entrenar un modelo openWakeWord propio para "Jarvis" pronunciado en
español (el entrenamiento necesita Linux/Colab).

## Anti-eco

El micrófono integrado capta los altavoces con fuerza (tono a volumen 100 % → −37 dBFS en el
micrófono). Estrategia (half-duplex):

1. Mientras JARVIS habla, el callback del micrófono descarta todo el audio (`mute`).
2. Al terminar: espera `echo_cooldown_ms` (400 ms) para la reverberación, vacía la cola
   y reactiva el micrófono.
3. Se reinician openWakeWord (5 frames de calentamiento) y el VAD.
4. Las respuestas con la palabra "Jarvis" no pueden despertarlo: el micrófono estaba silenciado.

Consecuencia: no se puede interrumpir a JARVIS mientras habla (barge-in). Opciones futuras:
cancelación de eco acústico (AEC) con referencia de la salida, auriculares, o el procesado
"Voice Clarity" de Windows (requiere captura en modo comunicaciones).

Test: `tests/test_pipeline.py::test_no_echo_loop_after_speaking`.

## Audio del equipo

| | Dispositivo | Notas |
|---|---|---|
| Micrófono | `Varios micrófonos (Realtek(R) Audio)` (array integrado) | volumen de Windows 28 %; el driver aplica una puerta de ruido (el silencio llega como cero digital, ~−97 dBFS) |
| Altavoces | `Altavoces (Realtek(R) Audio)` | volumen 100 % |
| Host API | MME | acepta 16 kHz directamente (Windows convierte); WASAPI exige 48 kHz |

Para usar unos auriculares: `JARVIS_AUDIO_INPUT_DEVICE=Redmi` (parte del nombre o índice de
`python -m app.audio --devices`). Con auriculares desaparece el eco.

## GPU y VRAM (RTX 4050 Laptop, 6 GB)

| Componente | VRAM |
|---|---|
| Escritorio / apps | ~1,0 GB |
| Ollama `qwen3:4b-instruct` (contexto 4096) | ~3,2 GB |
| Whisper `large-v3-turbo` int8_float16 | ~1,2 GB |
| **Total** | **~5,4 GB de 6,1 GB** |

openWakeWord, Silero VAD y Piper usan solo CPU.

**Juegos y GPU compartida:** con Minecraft en marcha (65 % del motor 3D) el rendimiento cayó
de forma drástica (STT 0,3 → 2,7 s; LLM primera frase 0,3 → 16 s). Si se juega a la vez, usar
`JARVIS_STT_DEVICE=cpu` o cerrar el juego. Pendiente para fases futuras: detectar la carga de
la GPU y degradar automáticamente.

## Latencia

Conversación simulada (`scripts/simulate_voice.py`: frases Piper inyectadas en tiempo real
en el pipeline real, sin otras cargas pesadas en la GPU):

| Frase | STT | LLM 1ª frase | TTS 1ª frase | Primer audio tras fin de voz* |
|---|---|---|---|---|
| "Jarvis, ¿cómo estás?" | 0,31 s | 0,29 s | 0,07 s | 0,67 s |
| "Jarvis." → "Dime hola." | 0,34 s | 0,18 s | 0,05 s | 0,57 s |
| "Jarvis, ¿qué es un agujero negro?" | 0,50 s | 0,17 s | 0,05 s | 0,72 s |

\* Desde que el VAD da la frase por terminada. Para saber que terminaste, el VAD espera
`vad_min_silence_ms` = 0,7 s de silencio, así que la **latencia percibida es ~1,3–1,4 s**
(objetivo < 1,5 s). Bajar `vad_min_silence_ms` a 500 ms la reduce, con más riesgo de
cortar frases con pausas.

- Wake word acústico: 1,4 ms y VAD 0,3 ms de CPU por bloque de 80 ms (~2 % de un núcleo).
- Ollama responde en streaming y Piper sintetiza frase a frase: JARVIS empieza a hablar
  con la primera frase mientras genera el resto.
- Carga inicial de `python -m app --voice`: ~10 s con modelos en caché (Whisper ~4 s,
  Piper ~3 s, precalentamiento de Ollama).

## Smart App Control

Smart App Control está **activado y se mantiene activado**. Incidencias encontradas:

| Binario | Resultado | Solución |
|---|---|---|
| `sklearn\svm\_liblinear.cp312-win_amd64.pyd` (scikit-learn, importado por el `__init__` de `openwakeword`) | **Bloqueado** (evento CodeIntegrity 3118 / 3077, sin firma) | No se usa el paquete `openwakeword`: sus modelos ONNX se ejecutan directamente con `onnxruntime` (`app/voice/wakeword.py`). scikit-learn y scipy desinstalados |
| `ruff.exe` (Fase 1) | Bloqueado | Eliminado del entorno |
| PortAudio (`sounddevice`), `onnxruntime`, `ctranslate2`, DLL de CUDA/cuDNN, `piper\espeakbridge.pyd`, PyAV | Permitidos | — |

Cómo diagnosticar un bloqueo: el error es `WinError 4551` / "Una directiva de Control de
aplicaciones bloqueó este archivo"; el fichero exacto aparece en el visor de eventos,
`Microsoft-Windows-CodeIntegrity/Operational` (eventos 3033/3077/3118).

## Comandos

```powershell
python -m app.audio --devices        # micrófonos y altavoces
python -m app.audio --record-test    # graba 5 s, mide RMS/pico/ruido/clipping, reproduce y borra
python -m app.voice --download-models
python -m app.voice --tts-test       # "Hola, soy Jarvis..."
python -m app.voice --vad-test       # muestra SILENCE / VOICE
python -m app.voice --stt-test       # "You said: ..."
python -m app.voice --wake-test      # "[detected] Jarvis"
python -m app --voice                # asistente completo
python -m app --voice --max-turns 3  # termina tras 3 respuestas
uv run python scripts/benchmark_stt.py
uv run python scripts/simulate_voice.py [--silent]
```

## Configuración

Todas en `config/jarvis.toml` (o `.env` con prefijo `JARVIS_`): dispositivos de audio,
`wake_engine`, `wake_aliases`, `wake_threshold`, `vad_*`, `listen_timeout_s`,
`max_utterance_s`, `stt_*`, `tts_voice`, `tts_length_scale`, `echo_cooldown_ms`,
`voice_max_reply_words`, `ollama_keep_alive`.

## Limitaciones conocidas

- Wake word acústico solo con pronunciación inglesa (mitigado con el modo híbrido).
- Sin barge-in (no se le puede interrumpir mientras habla).
- En habitaciones con conversaciones de fondo la orden puede mezclarse con otras voces
  (micrófono omnidireccional del portátil). Mejor con auriculares.
- Rendimiento muy degradado si un juego usa la GPU.
- JARVIS todavía no ejecuta acciones: solo conversa (las herramientas llegan en la Fase 3).
