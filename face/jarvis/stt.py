from pathlib import Path
import yaml
import numpy as np

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)

_model = None
_model_device = None  # track what device the model is on

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore

def _get_model(force_cpu=False):
    global _model, _model_device
    if _model is not None and not force_cpu:
        return _model
    cfg = _load_config()
    stt = cfg["stt"]
    device = "cpu" if force_cpu else stt["device"]
    compute_type = "int8" if force_cpu else stt["compute_type"]
    try:
        _model = WhisperModel(stt["model"], device=device, compute_type=compute_type)
        _model_device = device
        print(f"[STT] Loaded {stt['model']} on {device}")
    except Exception as e:
        if device != "cpu":
            print(f"[STT] {device} failed to load ({e}), falling back to CPU")
            _model = WhisperModel(stt["model"], device="cpu", compute_type="int8")
            _model_device = "cpu"
            print(f"[STT] Loaded {stt['model']} on cpu")
        else:
            raise
    return _model

# Frases que Whisper "alucina" con silencio o ruido (sobre todo en español).
_ALUCINACIONES = (
    "gracias por ver", "suscríbete", "subtítulos", "amara.org", "gracias por su atención",
    "thanks for watching", "thank you for watching",
)


def _transcribe(model, audio: np.ndarray) -> str:
    stt = _load_config()["stt"]
    segments, _ = model.transcribe(
        audio, beam_size=5, language=stt.get("language", "es"),
        initial_prompt=stt.get("prompt") or None, vad_filter=True,
        condition_on_previous_text=False,
    )
    partes = []
    for seg in segments:
        t = seg.text.strip()
        if seg.no_speech_prob > 0.8 or any(a in t.lower() for a in _ALUCINACIONES):
            continue
        partes.append(t)
    return " ".join(partes).strip()


def transcribe_audio(audio: np.ndarray) -> str:
    """Transcribe a float32 numpy audio array (16kHz mono) to text."""
    try:
        return _transcribe(_get_model(), audio)
    except Exception as e:
        # If CUDA worked for loading but fails during inference, retry on CPU
        if _model_device != "cpu":
            print(f"[STT] {_model_device} transcription failed ({e}), reloading on CPU")
            try:
                return _transcribe(_get_model(force_cpu=True), audio)
            except Exception as e2:
                print(f"[STT] CPU transcription also failed: {e2}")
                return ""
        print(f"[STT] Transcription failed: {e}")
        return ""

# Global abort event — set by main.py so recording can be interrupted
_abort_event = None

def set_abort_event(event) -> None:
    """Register the global abort event so recording checks it."""
    global _abort_event
    _abort_event = event

def record_until_silence(
    sample_rate: int = 16000,
    silence_threshold: float = 0.012,
    max_seconds: int = 30,
    start_timeout: float = 6.0,
) -> np.ndarray:
    """Graba del micrófono compartido (jarvis.mic) hasta detectar silencio. Devuelve float32 a 16 kHz.
    Espera a que empiece la voz antes de contar silencio. Los umbrales se adaptan al ruido de fondo
    que mide el hub. Se puede interrumpir con el evento de aborto."""
    import queue as _queue
    from jarvis.mic import get_hub, BLOCK

    hub = get_hub()
    floor = hub.noise_floor()
    speech_threshold = max(0.03, floor * 3.0)
    silence_threshold = max(silence_threshold, floor * 2.2)
    print(f"[STT] Ruido de fondo {floor:.4f} → voz ≥ {speech_threshold:.4f}, silencio < {silence_threshold:.4f}")

    per_window = 4  # 4 × 80 ms = 320 ms por ventana
    windows_needed = 6  # ~1,9 s de silencio para cortar
    recording: list[np.ndarray] = []
    window: list[np.ndarray] = []
    silent = 0
    heard_speech = False
    q = hub.subscribe(maxsize=int(max_seconds * sample_rate / BLOCK) + 8)
    try:
        while True:
            if _abort_event and _abort_event.is_set():
                print("[STT] Recording aborted.")
                break
            try:
                block = q.get(timeout=1.0).astype(np.float32) / 32768
            except _queue.Empty:
                continue
            recording.append(block)
            window.append(block)
            if len(window) < per_window:
                continue
            flat = np.concatenate(window)
            window = []
            rms = float(np.sqrt(np.mean(flat ** 2)))
            if rms >= speech_threshold:
                if not heard_speech:
                    print(f"[STT] Speech detected (rms={rms:.4f})")
                heard_speech = True
                silent = 0
            elif heard_speech and rms < silence_threshold:
                silent += 1
            seconds = len(recording) * BLOCK / sample_rate
            if heard_speech and silent >= windows_needed:
                print("[STT] Silence detected, stopping recording.")
                break
            if not heard_speech and seconds >= start_timeout:
                print("[STT] No se oyó voz.")
                break
            if seconds >= max_seconds:
                print(f"[STT] Max recording time reached ({max_seconds}s)")
                break
    finally:
        hub.unsubscribe(q)

    if not recording or not heard_speech:
        return np.zeros(BLOCK, dtype=np.float32)
    return np.concatenate(recording)
