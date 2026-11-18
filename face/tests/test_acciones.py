"""Atajos locales de música y volumen (D-016): qué frases se atienden sin cerebro y con qué búsqueda."""
import pytest

import jarvis.acciones as A


@pytest.fixture
def sp(monkeypatch):
    llam = {"buscar": [], "control": [], "vol": [], "sistema": []}
    monkeypatch.setattr(A.spotify, "poner", lambda cancion=None, artista=None: (llam["buscar"].append((cancion, artista)) or ("Tú y yo", "Artista X")))
    monkeypatch.setattr(A.spotify, "control", lambda a: llam["control"].append(a) or True)
    monkeypatch.setattr(A.spotify, "abierto", lambda: True)
    monkeypatch.setattr(A.spotify, "volumen", lambda: 0.5)
    monkeypatch.setattr(A.spotify, "fijar_volumen", lambda v: llam["vol"].append(round(v, 2)) or True)
    monkeypatch.setattr(A.ducking, "is_ducked", lambda: False)
    monkeypatch.setattr(A.ducking, "set_original", lambda app, v: False)
    monkeypatch.setattr(A, "_sistema", lambda delta=None, abs_=None: llam["sistema"].append((delta, abs_)))
    return llam


@pytest.mark.parametrize("frase,esperado", [
    ("Reproduce en Spotify tú y yo", ("tu y yo", None)),
    ("Pon música de Frankie Ruiz", (None, "frankie ruiz")),
    ("Ponme algo de Soda Stereo", (None, "soda stereo")),
    ("Reproduce De música ligera de Soda Stereo", ("de musica ligera", "soda stereo")),
    ("Quiero escuchar Despacito", ("despacito", None)),
])
def test_busquedas(sp, frase, esperado):
    texto, cerrar = A.intentar(frase)
    assert sp["buscar"] == [esperado] and cerrar and texto == "Reproduciendo «Tú y yo», de Artista X."
    assert "señor" not in texto


@pytest.mark.parametrize("frase,accion", [("pausa la música", "pause"), ("siguiente canción", "next"),
                                          ("continúa", "play"), ("la anterior", "previous")])
def test_controles(sp, frase, accion):
    A.intentar(frase)
    assert sp["control"] == [accion]


def test_volumen_es_de_spotify_por_defecto(sp):
    assert A.intentar("sube el volumen") == ("Música al 65 %.", True)
    assert A.intentar("pon la música al 30") == ("Música al 30 %.", True)
    assert sp["vol"] == [0.65, 0.3] and sp["sistema"] == []


def test_volumen_del_sistema_si_se_dice(sp):
    assert A.intentar("sube el volumen de la laptop")[0] == "Subo el volumen del sistema."
    assert sp["sistema"] and not sp["vol"]


@pytest.mark.parametrize("frase", ["abre la calculadora", "para", "¿qué tiempo hace mañana?", "pon una alarma a las 7",
                                   "pon un recordatorio para mañana", "ponme un vídeo de gatos en YouTube"])
def test_lo_demas_va_al_cerebro(sp, frase):
    assert A.intentar(frase) is None and sp["buscar"] == []
