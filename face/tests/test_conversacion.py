"""Activación por nombre y respuestas locales."""
import pytest

from jarvis.frases import clasificar, es_despedida
from jarvis.nombre import detectar


@pytest.mark.parametrize("t,resto", [
    ("Jarvis, ¿estás despierto?", "estás despierto"),
    ("Oye Jarvis, ¿qué hora es?", "qué hora es"),
    ("Yarvis, pon música.", "pon música"),
    ("Charvis abre la calculadora", "abre la calculadora"),
    ("Carbis, gracias, eso es todo.", "gracias, eso es todo"),
    ("Jarvis.", ""),
])
def test_llama(t, resto):
    assert detectar(t) == (True, resto)


@pytest.mark.parametrize("t", ["Ayer vi una película donde salía Jarvis.", "Travis llegó tarde.",
                               "Javier, ven aquí", "Voy a preparar la cena."])
def test_no_llama(t):
    assert detectar(t)[0] is False


def test_nombre_al_final_de_frase_corta():
    assert detectar("Hola, ¿qué tal Jarvis?")[0] is True


@pytest.mark.parametrize("resto,cat", [
    ("", "llamada"), ("¿estás despierto?", "presencia"), ("¿me oyes?", "presencia"),
    ("necesito que me ayudes", "ayuda"), ("tengo una pregunta", "ayuda"), ("gracias", "gracias"),
])
def test_clasificar_local(resto, cat):
    assert clasificar(resto) == cat


def test_saludo_segun_hora():
    assert clasificar("buenas").startswith("saludo_")


@pytest.mark.parametrize("orden", ["abre la calculadora", "necesito que me ayudes con un correo",
                                   "¿qué tiempo hace mañana?"])
def test_ordenes_van_al_cerebro(orden):
    assert clasificar(orden) is None


@pytest.mark.parametrize("t", ["gracias, eso es todo", "Ya está.", "cierra la conversación", "nada más, gracias"])
def test_despedidas(t):
    assert es_despedida(t)


def test_no_despedida():
    assert not es_despedida("ya está listo el documento que te pedí ayer por la tarde")
