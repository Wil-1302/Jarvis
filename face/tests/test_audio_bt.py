"""Regresión del 18/11: parlante Bluetooth Alaxe (se anuncia como «headset») y nombre mal transcrito."""
import types

from jarvis import eco
from jarvis.nombre import detectar

ALAXE = {"name": "bluez_output.1F_D6_84_33_C9_2E.1", "description": "Alaxe", "active_port": "headset-output",
         "properties": {"device.form_factor": "headset", "device.description": "Alaxe",
                        "api.bluez5.address": "1F:D6:84:33:C9:2E", "device.bus": "bluetooth"}}
ALTAVOZ = {"name": "alsa_output.pci-0000_05_00.6.analog-stereo", "description": "Ryzen HD Audio Controller",
           "active_port": "analog-output-speaker", "properties": {}}


def test_alaxe_sin_lista_parece_audifonos():
    assert eco.es_audifonos(ALAXE)


def test_lista_de_parlantes_manda():
    for e in ("Alaxe", "alaxe", "bluez_output.1F_D6", "1F:D6:84:33:C9:2E"):
        assert not eco.es_audifonos(ALAXE, parlantes=[e]), e


def test_lista_de_audifonos_manda():
    assert eco.es_audifonos(ALTAVOZ, audifonos=["Ryzen HD"])
    assert not eco.es_audifonos(ALTAVOZ, audifonos=["", "  "])


def test_barge_in_auto_solo_con_audifonos():
    from jarvis.conversacion import Conversacion
    c = types.SimpleNamespace(barge_in="auto")
    f = Conversacion._barge_in_activo
    assert f(c, types.SimpleNamespace(estado_filtro="audífonos"))
    for e in ("activo", "apagado", "sin-librería"):
        assert not f(c, types.SimpleNamespace(estado_filtro=e)), e


def test_formas_del_nombre_en_las_grabaciones():
    for t in ("Y Arby, ¿estás despierto?", "Y Arby's, ¿Estás Despierto?", "Y Arbis, ¿está despierto?",
              "Yervis, ¿estás despierto?", "Y ya arvisita, despierta.", "Y Arvis, ¿estás despierto?"):
        assert detectar(t)[0], t
    for t in ("Ya, pon música", "Javier, ven aquí", "Ya, mixto es al izquierdo."):
        assert not detectar(t)[0], t


def test_entrar_no_hereda_un_plazo_caducado(monkeypatch):
    import threading
    from jarvis import conversacion as cv
    monkeypatch.setattr(cv.ducking, "duck", lambda *a: None)
    c = types.SimpleNamespace(_lock=threading.Lock(), estado=cv.ESPERA, deadline=0.0, duck_factor=0.2)
    cv.Conversacion._entrar(c)
    assert c.estado == cv.CONVERSACION and c.deadline == float("inf")


def test_segunda_opinion_con_el_audio_original():
    import numpy as np
    from jarvis.conversacion import Conversacion
    hub = types.SimpleNamespace(filtrando=True, tramo=lambda a, b: np.ones(b - a, np.int16))
    c = types.SimpleNamespace(hub=hub, stt_fuente="limpio", debug=False)
    u = types.SimpleNamespace(i0=100, audio=np.zeros(1600, np.float32))
    llama, resto, texto, _ = Conversacion._segunda_opinion(c, u, lambda a: "Jarvis, ¿estás despierto?", "Y ahora", 0.4)
    assert llama and resto == "estás despierto"
    hub.filtrando = False   # sin filtro el original es lo mismo: no se repite
    assert not Conversacion._segunda_opinion(c, u, lambda a: "Jarvis", "Y ahora", 0.4)[0]


def test_filtro_off_en_yaml_sin_comillas():
    import yaml
    from jarvis.mic import modo_filtro
    for txt in ("off", "no", "false", '"off"', "False"):
        assert modo_filtro(yaml.safe_load(f"v: {txt}")["v"]) == "off", txt
    for txt in ("auto", '"auto"', "on", "true"):
        assert modo_filtro(yaml.safe_load(f"v: {txt}")["v"]) == "auto", txt


def test_vad_reinicia_silero_tras_silencio():
    import numpy as np
    from jarvis import vad as V
    resets = []
    class Falso:
        def __call__(self, fr): return 0.0
        def reset(self): resets.append(1)
    real = V.SileroVAD
    V.SileroVAD = Falso
    try:
        seg = V.Segmenter(end_silence=0.45, reinicio_silencio=3.0)
        resets.clear()
        seg.feed(np.zeros(16000 * 10, np.int16), now=0.0, i0=0)   # 10 s de silencio
        assert len(resets) == 3
    finally:
        V.SileroVAD = real
