import pytest
from jarvis.enrutador import elegir, tipo

CFG = {"llm": {"enrutado": {"activo": True, "charla": "openai/gpt-5.6-terra", "trabajo": "anthropic/claude-sonnet-5-5"}}}


@pytest.mark.parametrize("t", ["¿Qué tal tu día?", "Cuéntame un cuento para dormir", "¿Por qué el cielo es azul?",
                               "Dame un consejo para estudiar mejor", "Hola, ¿cómo estás?"])
def test_charla(t):
    assert tipo(t) == "charla" and elegir(t, CFG)[:2] == ("openai/gpt-5.6-terra", "anthropic/claude-sonnet-5-5")


@pytest.mark.parametrize("t", ["Escríbeme un script en Python que renombre fotos", "Crea un documento con la receta",
                               "Abre la calculadora", "¿Qué tiempo hará mañana en Madrid?",
                               "Recuérdame llamar a mi madre a las 8", "Busca el precio del dólar hoy"])
def test_trabajo(t):
    assert tipo(t) == "trabajo" and elegir(t, CFG)[0] == "anthropic/claude-sonnet-5-5"


def test_apagado():
    assert elegir("hola", {"llm": {"enrutado": {"activo": False}}})[0] is None


# Regresión: una orden de música que se le escape al atajo local nunca va a la vía ligera de charla.
@pytest.mark.parametrize("t", ["Ponte unas músicas para sufrir", "pon algo para bailar", "¿Qué canción está sonando?",
                               "Ahora reproduce duels de Jessie Joy", "Ponme una playlist para estudiar",
                               "Hazme una presentación en Canva sobre el reciclaje", "Busca imágenes de volcanes"])
def test_musica_y_creacion_nunca_van_a_charla(t):
    assert tipo(t) == "trabajo"
