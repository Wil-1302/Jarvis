# jarvis/tests/test_stt.py
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

STUB_CONFIG = {
    "stt": {"model": "turbo", "device": "cuda", "compute_type": "float16", "language": "es"}
}


def _seg(text, nsp=0.0):
    s = MagicMock(); s.text = text; s.no_speech_prob = nsp
    return s

def test_transcribe_returns_string():
    """transcribe_audio should return a string for valid audio."""
    with patch("jarvis.stt._load_config", return_value=STUB_CONFIG), \
         patch("jarvis.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_segment = _seg(" hello world")
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_model_cls.return_value = mock_model
        # Reset module singleton so new mock takes effect
        import jarvis.stt as stt_mod
        stt_mod._model = None

        from jarvis.stt import transcribe_audio
        fake_audio = np.zeros(16000, dtype=np.float32)
        result = transcribe_audio(fake_audio)
        assert isinstance(result, str)

def test_transcribe_strips_whitespace():
    """transcribe_audio should return clean stripped text."""
    with patch("jarvis.stt._load_config", return_value=STUB_CONFIG), \
         patch("jarvis.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_segment = _seg("  hello world  ")
        mock_model.transcribe.return_value = ([mock_segment], None)
        mock_model_cls.return_value = mock_model
        import jarvis.stt as stt_mod
        stt_mod._model = None

        from jarvis.stt import transcribe_audio
        fake_audio = np.zeros(16000, dtype=np.float32)
        result = transcribe_audio(fake_audio)
        assert result == "hello world"

def test_transcribe_concatenates_segments():
    """transcribe_audio should join multiple segments."""
    with patch("jarvis.stt._load_config", return_value=STUB_CONFIG), \
         patch("jarvis.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        seg1 = _seg("hello"); seg2 = _seg(" world")
        mock_model.transcribe.return_value = ([seg1, seg2], None)
        mock_model_cls.return_value = mock_model
        import jarvis.stt as stt_mod
        stt_mod._model = None

        from jarvis.stt import transcribe_audio
        result = transcribe_audio(np.zeros(16000, dtype=np.float32))
        assert result == "hello world"


def test_filtra_alucinaciones_y_silencio():
    """Whisper inventa 'Gracias por ver el video.' con silencio: se descarta, igual que no_speech_prob alto."""
    with patch("jarvis.stt._load_config", return_value=STUB_CONFIG), \
         patch("jarvis.stt.WhisperModel") as mock_model_cls:
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            [_seg("abre Spotify"), _seg(" Gracias por ver el video."), _seg(" ruido", 0.95)], None)
        mock_model_cls.return_value = mock_model
        import jarvis.stt as stt_mod
        stt_mod._model = None
        assert stt_mod.transcribe_audio(np.zeros(16000, dtype=np.float32)) == "abre Spotify"
        assert mock_model.transcribe.call_args.kwargs["language"] == "es"
