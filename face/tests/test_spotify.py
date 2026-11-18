"""Spotify (D-016, D-018): Web API opcional con búsqueda por artista y caída a la app de escritorio."""
import httpx
import pytest

import jarvis.spotify as S


@pytest.fixture(autouse=True)
def limpio(monkeypatch):
    monkeypatch.setattr(S, "_api_inutil", False)
    esc = []
    monkeypatch.setattr(S, "reproducir_busqueda", lambda q, por_artista=False: esc.append((q, por_artista)) or True)
    monkeypatch.setattr(S, "sonando", lambda: ("Crimen", "Gustavo Cerati"))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    return esc


def _pista(nombre, *artistas):
    return {"uri": f"spotify:track:{nombre}", "name": nombre, "artists": [{"name": a} for a in artistas]}


def test_artista_busca_por_artista_sin_top_tracks(monkeypatch):
    pedidos = []

    def get(path, **p):
        pedidos.append((path, p))
        return {"tracks": {"items": [_pista("Otro", "Imitador"), _pista("Crimen", "Gustavo Cerati")]}}

    monkeypatch.setattr(S, "_get", get)
    assert S.buscar(artista="gustavo cerati") == ("spotify:track:Crimen", "Crimen", "Gustavo Cerati")
    assert pedidos == [("search", {"q": 'artist:"gustavo cerati"', "type": "track", "limit": 10, "market": "PE"})]
    assert not any("top-tracks" in p for p, _ in pedidos)


def test_sin_credenciales_usa_el_escritorio(monkeypatch, limpio):
    monkeypatch.setattr(S, "_leer_env", lambda n: "")
    assert S.poner(artista="gustavo cerati") == ("Crimen", "Gustavo Cerati")
    assert limpio == [("gustavo cerati", True)] and S._api_inutil


def test_403_sin_premium_usa_el_escritorio_y_no_reintenta(monkeypatch, limpio):
    llamadas = []

    def buscar(**kw):
        llamadas.append(kw)
        raise httpx.HTTPStatusError("403", request=httpx.Request("GET", "https://x"), response=httpx.Response(403))

    monkeypatch.setattr(S, "buscar", buscar)
    S.poner(cancion="de musica ligera", artista="soda stereo")
    S.poner(cancion="vivo")
    assert len(llamadas) == 1
    assert limpio == [("de musica ligera soda stereo", False), ("vivo", False)]


def test_api_que_funciona_no_toca_el_escritorio(monkeypatch, limpio):
    monkeypatch.setattr(S, "buscar", lambda **kw: ("spotify:track:x", "Vivo", "Gustavo Cerati"))
    monkeypatch.setattr(S, "reproducir", lambda uri: True)
    assert S.poner(cancion="vivo") == ("Vivo", "Gustavo Cerati") and limpio == []
