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


def _prompt(stt: dict) -> str | None:
    """Vocabulario del señor (D-025: ~/.config/jarvis/vocabulario.txt, privado) o el prompt fijo de config.yaml."""
    if stt.get("vocabulario", True):
        try:
            from jarvis.vocabulario import prompt
            return prompt()
        except Exception:
            pass
    return stt.get("prompt") or None


def _transcribe(model, audio: np.ndarray) -> str:
    stt = _load_config()["stt"]
    segments, _ = model.transcribe(
        audio, beam_size=int(stt.get("beam_size", 1)), language=stt.get("language", "es"),
        initial_prompt=_prompt(stt), vad_filter=True,
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
