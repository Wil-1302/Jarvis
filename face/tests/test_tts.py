"""Voz: motor intercambiable, reproductor persistente y habla en streaming por oraciones."""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

import jarvis.tts as T


class _Eng:
    rate = 24000
    name = "fake"

    def __init__(self):
        self.dichas = []

    def synth(self, text):
        self.dichas.append(text)
        return np.ones(240, np.float32) * 0.1


@pytest.fixture
def eng(monkeypatch):
    e = _Eng()
    monkeypatch.setattr(T, "_engine", e)
    monkeypatch.setattr(T.player, "play", MagicMock(return_value=True))
    monkeypatch.setattr(T.player, "drain", MagicMock())
    return e


def test_speak_to_bytes(eng):
    b = T.speak_to_bytes("Hola, señor.")
    assert isinstance(b, bytes) and len(b) == 480


@pytest.mark.parametrize("t", ["", "   "])
def test_rechaza_vacio(eng, t):
    with pytest.raises(ValueError):
        T.speak_to_bytes(t)


def test_speak_reproduce(eng):
    T.speak("Motores listos.")
    T.player.play.assert_called_once()
    assert eng.dichas == ["Motores listos."]


def test_stream_corta_por_oraciones_y_quita_markdown(eng):
    trozos = ["Buenas ", "noches, **señor**. Todo", " en orden", ". ¿Algo ", "más?"]
    full = T.speak_stream(iter(trozos))
    assert full == "".join(trozos)
    assert eng.dichas == ["Buenas noches, señor.", "Todo en orden.", "¿Algo más?"]
    assert T.player.play.call_count == 3


def test_stream_primer_audio_avisa(eng):
    visto = []
    T.speak_stream(iter(["Hola."]), on_first_audio=lambda: visto.append(1))
    assert visto == [1]


def test_respaldo_piper_si_edge_falla(capsys):
    class Mala:
        name = "edge-x"
        def synth(self, t):
            raise TimeoutError("sin internet")
    class Piper(_Eng):
        name = "piper-x"
    e = T.FallbackEngine(lambda: Mala(), Piper(), cooldown=60)
    assert e.synth("Hola.").size and e.last_was_backup
    assert "respaldo piper-x" in capsys.readouterr().out
    e.synth("Otra.")                      # durante el cooldown ni se intenta el principal
    assert e.backup.dichas == ["Hola.", "Otra."]


def test_azure_ssml_escapa_y_aplica_prosodia(monkeypatch):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k" * 32)
    monkeypatch.setenv("AZURE_SPEECH_REGION", "eastus")
    a = T.AzureEngine({"tts": {"edge": {"voice": "es-MX-JorgeNeural", "rate": "-8%", "pitch": "-2Hz"}}})
    x = a.ssml("Café & <té>")
    assert 'name="es-MX-JorgeNeural"' in x and 'rate="-8%"' in x and "Café &amp; &lt;té&gt;" in x
