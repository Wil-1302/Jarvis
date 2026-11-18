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


def test_pausa_del_cerebro_dice_lo_recibido(eng):
    T.speak_stream(iter(["Voy a buscarlo", T.FLUSH, T.FLUSH, " ahora mismo. Listo."]))
    assert eng.dichas == ["Voy a buscarlo", "ahora mismo.", "Listo."]


# --- Prosa hablada: el Markdown no llega a la voz (también al vuelo, carácter a carácter) ---
import pytest as _pytest
from jarvis.tts import FiltroProsa, _clean, prosa


@_pytest.mark.parametrize("md,voz", [
    ("Te propongo tres cenas:\n\n1. **Tortilla**: rápida.\n2. Pasta con *pesto*\n3. Ensalada 🥗\n\nBuen provecho.",
     "Te propongo tres cenas: Tortilla: rápida. Pasta con pesto. Ensalada. Buen provecho."),
    ("## Clima en Lima\n- Hoy: 22 °C\n- Mañana: 24 °C", "Clima en Lima. Hoy: 22 °C. Mañana: 24 °C"),
    ("Mira:\n```bash\nls -la\n```\nEso lista los archivos.", "Mira: Eso lista los archivos."),
    ("| Día | Máx |\n|---|---|\n| Lunes | 22 |\n", "Día, Máx. Lunes, 22."),
    ("Antes\n- - -\ndespués", "Antes. después"),
    ("En 2024 hubo -5 grados y 3.5 millones de *personas*.", "En 2024 hubo -5 grados y 3.5 millones de personas."),
    ("snake_case_var y [la web](https://x.y) o https://x.y/z.", "snake_case_var y la web o."),
])
def test_markdown_a_prosa(md, voz):
    assert _clean(prosa(md)) == voz
    f = FiltroProsa()
    assert _clean("".join(f.feed(c) for c in md) + f.flush()) == voz
