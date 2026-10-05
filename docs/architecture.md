# JARVIS-WIL — Arquitectura

Estado: **Fase 2** (motor de voz local). Repositorio: `git@github.com:Wil-1302/Jarvis.git`.

## Vista general

```
                ┌──────────────────────── app/cli.py ────────────────────────┐
                │  python -m app          python -m app --voice    --health   │
                └──────┬─────────────────────────┬──────────────────┬─────────┘
                       │                         │                  │
              app/core/jarvis.py        app/voice/pipeline.py   app/core/health.py
              (consola de texto)        (VoicePipeline)
                                                 │
   ┌──────────────┬──────────────┬───────────────┼──────────────┬───────────────┐
   │              │              │               │              │               │
app/audio/    app/voice/     app/voice/      app/voice/     app/brain/      app/voice/
stream.py     wakeword.py    vad.py          stt.py         conversation.py tts.py
Micrófono /   openWakeWord   Silero VAD +    faster-whisper Ollama          Piper
Altavoces     (ONNX)         segmentador     (CUDA)         (streaming)     (ONNX)
                                                 │
                                         app/voice/state.py
                                         (máquina de estados)

app/config/settings.py   configuración central (entorno > .env > config/jarvis.toml > defaults)
app/core/logging.py      logs/jarvis.log rotativo con redacción de secretos
app/voice/models.py      descarga y rutas de modelos (models/)
```

## Módulos

| Módulo | Responsabilidad |
|---|---|
| `app/config/settings.py` | `Settings` tipado (pydantic-settings); identidad, LLM, logging, permisos, audio y voz |
| `app/core/logging.py` | logger `jarvis`, fichero rotativo, filtro que oculta API keys y tokens |
| `app/core/health.py` | 12 comprobaciones del entorno (Python, Ollama, FFmpeg, Git, audio, modelos, CUDA…) |
| `app/core/jarvis.py` | núcleo de la consola de texto (Fase 1) |
| `app/audio/device_manager.py` | listar, buscar y validar dispositivos (host API MME por defecto) |
| `app/audio/stream.py` | `MicrophoneStream` (callback → cola, con `mute` anti-eco), `AudioPlayer`, `record` |
| `app/audio/analysis.py` | RMS, pico, ruido de fondo, clipping y detección de señal |
| `app/voice/wakeword.py` | `WakeWordDetector` (openWakeWord en ONNX) y `match_wake_word` (por transcripción) |
| `app/voice/vad.py` | `SileroVAD` (streaming, 32 ms) y `SpeechSegmenter` (SILENCE → VOICE → SILENCE) |
| `app/voice/stt.py` | `SpeechToText` (faster-whisper, CUDA con fallback a CPU, filtro de alucinaciones) |
| `app/voice/tts.py` | `TextToSpeech` (Piper, síntesis frase a frase, limpieza de markdown y emojis) |
| `app/voice/state.py` | `StateMachine` con transiciones válidas, historial y listeners |
| `app/voice/pipeline.py` | `VoicePipeline` (orquesta un turno, anti-eco, métricas) y `build_pipeline` |
| `app/voice/simulation.py` | `SimulatedSource`: frases sintéticas como si fueran el micrófono (tests) |
| `app/brain/ollama_client.py` | cliente HTTP de Ollama (chat, streaming, precarga) |
| `app/brain/conversation.py` | `ConversationBrain`: prompt de sistema en español, historial corto, división en frases |

## Decisiones de diseño

- **Un hilo de procesado.** PortAudio solo encola bloques; el bucle de `VoicePipeline.run`
  procesa en orden. Más simple y suficiente: el micrófono está silenciado mientras JARVIS habla.
- **Interfaces mínimas (Protocol)** para fuente de audio, STT, TTS, cerebro y reproductor:
  el pipeline se prueba entero con dobles (`tests/voice_fakes.py`), sin hardware.
- **Streaming de extremo a extremo:** Ollama genera, `split_sentences` corta frases y Piper
  sintetiza la siguiente mientras suena la anterior.
- **Modelos fuera de git** (`models/`), descargados bajo demanda desde las fuentes oficiales.
- **Sin dependencias bloqueadas por Smart App Control**: se evitan los paquetes cuyos binarios
  nativos bloquea (scikit-learn) y se usan los modelos ONNX directamente.
- **Proyecto solo Windows:** `[tool.uv] environments = ["sys_platform == 'win32'"]`.

## Dependencias de runtime

`pydantic-settings`, `httpx`, `numpy`, `sounddevice`, `faster-whisper` (arrastra `ctranslate2`,
`onnxruntime`, `av`, `tokenizers`, `huggingface-hub`), `nvidia-cublas-cu12`, `nvidia-cudnn-cu12`,
`piper-tts`. Desarrollo: `pytest`.

## Próximas fases

Ver `docs/PROJECT_PLAN.md`: herramientas de Windows y Spotify (Fase 3), app de bandeja
(Fase 4), MCP y memoria (Fase 5), orquestación de Claude Code (Fase 6).
