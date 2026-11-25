"""Agenda (D-030/D-031): umbrales, sin repetir, entregadas, pospuestas, silencio y órdenes locales. Sin red."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jarvis import agenda as ag

LIMA = ZoneInfo("America/Lima")
AHORA = datetime(2026, 11, 24, 14, 0, tzinfo=LIMA)   # martes


def tarea(i, horas, titulo="Informe", curso="Redes"):
    return {"id": f"c/{i}", "titulo": titulo, "curso": curso, "vence": (AHORA + timedelta(hours=horas)).isoformat()}


def est():
    return ag.cargar(ruta=__import__("pathlib").Path("/nonexistent/x.json"))


def test_umbral():
    assert ag.umbral(30, [24, 6, 2]) is None
    assert ag.umbral(20, [24, 6, 2]) == 24
    assert ag.umbral(5, [24, 6, 2]) == 6
    assert ag.umbral(1.5, [24, 6, 2]) == 2


def test_cada_umbral_una_vez_y_sin_rafaga():
    e = est()
    t = [tarea(1, 20)]
    assert len(ag.a_avisar(t, e, AHORA, [24, 6, 2])) == 1
    assert ag.a_avisar(t, e, AHORA + timedelta(minutes=15), [24, 6, 2]) == []   # no repite
    # tarea nueva a 3 h: un solo aviso (el de 6 h), y el de 2 h llega después
    e2 = est()
    t2 = [tarea(2, 3)]
    assert len(ag.a_avisar(t2, e2, AHORA, [24, 6, 2])) == 1
    assert ag.a_avisar(t2, e2, AHORA + timedelta(minutes=30), [24, 6, 2]) == []
    assert len(ag.a_avisar(t2, e2, AHORA + timedelta(hours=1, minutes=5), [24, 6, 2])) == 1


def test_vencidas_y_entregadas_no_se_avisan():
    e = est()
    e["entregadas"]["c/1"] = AHORA.isoformat()
    assert ag.a_avisar([tarea(1, 2), tarea(3, -1)], e, AHORA, [24, 6, 2]) == []


def test_entregada_tras_aviso():
    e = est()
    lista = ag.a_avisar([tarea(1, 5)], e, AHORA, [24, 6, 2])
    e["ultimo"] = {"t": AHORA.isoformat(), "tipo": "tareas", "ids": [t["id"] for t in lista]}
    r = ag.responder("Ya la entregué.", e, AHORA + timedelta(minutes=2))
    assert r and "no se la recordaré" in r
    assert ag.a_avisar([tarea(1, 5)], e, AHORA + timedelta(hours=4), [24, 6, 2]) == []


def test_posponer_una_hora():
    e = est()
    ag.a_avisar([tarea(1, 5)], e, AHORA, [24, 6, 2])
    e["ultimo"] = {"t": AHORA.isoformat(), "tipo": "tareas", "ids": ["c/1"]}
    r = ag.responder("Recuérdamelo en una hora", e, AHORA)
    assert r and "15:00" not in r and "las 3 de la tarde" in r
    assert ag.a_avisar([tarea(1, 5)], e, AHORA + timedelta(minutes=30), [24, 6, 2]) == []
    assert len(ag.a_avisar([tarea(1, 5)], e, AHORA + timedelta(minutes=61), [24, 6, 2])) == 1


def test_ordenes_sin_aviso_reciente_van_al_cerebro():
    e = est()
    assert ag.responder("ya la entregué", e, AHORA) is None
    assert ag.responder("recuérdamelo en una hora", e, AHORA) is None
    e["ultimo"] = {"t": (AHORA - timedelta(hours=2)).isoformat(), "tipo": "tareas", "ids": ["c/1"]}
    assert ag.responder("ya la entregué", e, AHORA) is None
    assert ag.responder("recuérdame el viernes a las 3 entregar el informe", est(), AHORA) is None


@pytest.mark.parametrize("frase,esperado", [
    ("Jarvis, no molestes hasta las 6", datetime(2026, 11, 24, 18, 0, tzinfo=LIMA)),
    ("no me molestes hasta las 6 de la mañana", datetime(2026, 11, 25, 6, 0, tzinfo=LIMA)),
    ("no molestes hasta las 4 y media", datetime(2026, 11, 24, 16, 30, tzinfo=LIMA)),
    ("no molestes hasta las 20:15", datetime(2026, 11, 24, 20, 15, tzinfo=LIMA)),
    ("no molestes hasta mañana", datetime(2026, 11, 25, 7, 0, tzinfo=LIMA)),
    ("no molestes hasta mañana a las 9", datetime(2026, 11, 25, 9, 0, tzinfo=LIMA)),
    ("no molestes en media hora", AHORA + timedelta(minutes=30)),
    ("modo no molestar", AHORA + timedelta(hours=1)),
])
def test_no_molestar(frase, esperado):
    e = est()
    r = ag.responder(frase, e, AHORA)
    assert r and "sin voz" in r
    assert datetime.fromisoformat(e["no_molestar_hasta"]) == esperado
    assert ag.en_silencio(AHORA + timedelta(minutes=1), {}, e) == "no molestar"
    assert ag.en_silencio(esperado + timedelta(minutes=1), {}, e) is None


def test_ya_puedes_molestar():
    e = est()
    ag.responder("no molestes hasta las 6", e, AHORA)
    assert ag.responder("ya puedes molestarme", e, AHORA)
    assert e["no_molestar_hasta"] is None


def test_silencio_noche_y_clases():
    cfg = {"silencio": {"noche": "22:30-07:00", "clases": [{"dias": ["mar", "jue"], "horas": "13:00-15:00"}]}}
    e = est()
    assert ag.en_silencio(AHORA, cfg, e) == "clase"                        # martes 14:00
    assert ag.en_silencio(AHORA + timedelta(days=1), cfg, e) is None       # miércoles 14:00
    assert ag.en_silencio(AHORA.replace(hour=23), cfg, e) == "noche"
    assert ag.en_silencio(AHORA.replace(hour=6, minute=59), cfg, e) == "noche"
    assert ag.en_silencio(AHORA.replace(hour=7), cfg, e) is None


def test_frase_y_cuando():
    assert ag.cuando(AHORA.replace(hour=23, minute=59), AHORA) == "hoy a las 11:59 de la noche"
    assert ag.cuando(AHORA + timedelta(days=1, hours=1), AHORA) == "mañana a las 3 de la tarde"
    assert ag.cuando(datetime(2026, 11, 27, 8, 0, tzinfo=LIMA), AHORA) == "el viernes 27 a las 8 de la mañana"
    f = ag.frase_aviso([tarea(1, 5), tarea(2, 20, "Ensayo", "Lengua")], AHORA)
    assert f.startswith("Señor, le faltan estas actividades: «Informe», de Redes, para hoy a las 7 de la noche")
    assert f.endswith("¿Empezamos? Estoy dispuesto a ayudarle.")
    assert ag.frase_aviso([tarea(1, 5)], AHORA).startswith("Señor, le falta esta actividad:")


def test_alarmas_proximas_una_vez():
    e = est()
    ev = [{"id": "e1", "summary": "Entregar el informe", "start": {"dateTime": (AHORA + timedelta(minutes=3)).isoformat()}},
          {"id": "e2", "summary": "Lejos", "start": {"dateTime": (AHORA + timedelta(hours=3)).isoformat()}},
          {"id": "e3", "summary": "Todo el día", "start": {"date": "2026-11-24"}}]
    p = ag.alarmas_proximas(ev, e, AHORA, 6)
    assert [x["id"] for x in p] == ["e1"]
    e["alarmas"][p[0]["clave"]] = AHORA.isoformat()
    assert ag.alarmas_proximas(ev, e, AHORA, 6) == []


def test_posponer_alarma():
    e = est()
    e["ultimo"] = {"t": AHORA.isoformat(), "tipo": "alarma", "ids": ["e1"], "titulo": "Entregar el informe"}
    assert ag.responder("recuérdamelo en 10 minutos", e, AHORA)
    assert e["alarmas_pospuestas"]["e1"]["t"] == (AHORA + timedelta(minutes=10)).isoformat()


def test_estado_600(tmp_path):
    r = tmp_path / "s" / "agenda.json"
    e = est()
    ag.guardar(e, r)
    assert oct(r.stat().st_mode & 0o777) == "0o600"
    assert ag.cargar(r)["avisados"] == {}
