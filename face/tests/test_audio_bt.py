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
