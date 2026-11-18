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


@pytest.mark.parametrize("t", ["gracias, eso es todo", "Ya está.", "cierra la conversación", "nada más, gracias",
                               "Adiós.", "Eso es todo.", "Ya.", "Gracias.", "Termina.", "Cierra conversación.",
                               "Cierra la conversación, por favor.", "Adiós, Jarvis.", "Ok, gracias, Jarvis.",
                               "Vale, eso es todo por hoy.", "Muchas gracias, hasta luego.", "Bueno, ya.",
                               "Listo, gracias.", "No, gracias.", "Termina la conversación.", "Hasta mañana."])
def test_despedidas(t):
    assert es_despedida(t)


@pytest.mark.parametrize("t", ["ya está listo el documento que te pedí ayer por la tarde",
                               "Gracias por la receta, ¿y el postre?", "Cierra la calculadora.",
                               "Ya sé qué quiero cenar.", "Termina el informe y mándamelo.", "¿Qué hora es?",
                               "Bueno, y ¿qué tiempo hace mañana?", ""])
def test_no_despedida(t):
    assert not es_despedida(t)


# --- Fin de frase adaptativo (D-024) y cierre de verdad (D-022) ---
import queue as _queue
import threading as _threading
import types

import numpy as _np

from jarvis.conversacion import Conversacion, ESPERA
from jarvis.frases import frase_incompleta
from jarvis.vad import Utterance


@pytest.mark.parametrize("t,inc", [("Jarvis, pon música de", True), ("Quiero que me digas y...", True),
                                   ("Jarvis, ¿qué tiempo hace hoy?", False), ("Pon algo de música, pero", True),
                                   ("Jarvis.", False), ("Jarvis, apunta comprar pan,", True),
                                   ("Abre la calculadora.", False), ("Dame una idea para", True)])
def test_frase_incompleta(t, inc):
    assert frase_incompleta(t) is inc


def _stub(textos, espera=0.3):
    q = _queue.Queue()
    st = types.SimpleNamespace(q=q, sordo_hasta=0.0, ocupado=_threading.Event(), verif=None, exento=False,
                               estado=ESPERA, espera_incompleta=espera, debug=False)
    it = iter(textos)
    return st, q, (lambda audio: next(it))


def _u(t0, t1):
    return Utterance(_np.zeros(int((t1 - t0) * 16000), _np.float32), t0, t1, t1 + 0.45)


def test_une_frase_a_medias_con_su_continuacion():
    st, q, tr = _stub(["Jarvis, pon música de", "Gustavo Cerati."])
    q.put(_u(1.0, 2.0)); q.put(_u(2.8, 3.6))
    u, texto, _, hablando = Conversacion._siguiente(st, tr)
    assert texto == "Jarvis, pon música de Gustavo Cerati." and not hablando and u.t_start == 1.0 and u.t_end == 3.6


def test_frase_a_medias_sin_continuacion_se_atiende_tras_el_plazo():
    st, q, tr = _stub(["Jarvis, dame una idea para"], espera=0.2)
    q.put(_u(1.0, 2.0))
    import time
    t0 = time.time()
    _, texto, _, _ = Conversacion._siguiente(st, tr)
    assert texto == "Jarvis, dame una idea para" and 0.15 < time.time() - t0 < 1.0


def test_tras_cerrar_se_ignora_lo_que_empezo_antes():
    st, q, tr = _stub(["Jarvis, abre la calculadora."])
    st.sordo_hasta = 5.0
    q.put(_u(4.0, 5.5)); q.put(_u(6.0, 7.0))
    u, texto, _, _ = Conversacion._siguiente(st, tr)
    assert u.t_start == 6.0 and texto == "Jarvis, abre la calculadora."
