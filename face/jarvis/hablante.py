"""Verificación de hablante: JARVIS solo atiende la voz del señor (D-015).

- Modelo: NeMo TitaNet small (ONNX, 40 MB) vía sherpa-onnx, en CPU (~20 ms por frase). Elegido frente a
  WeSpeaker ResNet34 y CAM++ (EER 5 % frente a 26–31 % con 10 voces sintéticas).
- Huella: ~/.config/jarvis/voz.npz (600, carpeta 700). Solo vectores (embeddings), NUNCA audio. No sale del
  equipo, no está en el repo y el gateway no puede leerla (InaccessiblePaths).
- Se verifica ANTES de transcribir: la voz de otra persona ni se transcribe ni se envía a ningún sitio.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

RATE = 16000
MODELO = Path(os.path.expanduser("~/.local/share/jarvis/voz-modelos/nemo_en_titanet_small.onnx"))
HUELLA = Path(os.environ.get("JARVIS_HUELLA", Path.home() / ".config" / "jarvis" / "voz.npz"))


class Extractor:
    def __init__(self, modelo: Path = MODELO):
        import sherpa_onnx as so
        self.ex = so.SpeakerEmbeddingExtractor(so.SpeakerEmbeddingExtractorConfig(model=str(modelo), num_threads=2))

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        s = self.ex.create_stream()
        s.accept_waveform(RATE, np.ascontiguousarray(audio, dtype=np.float32))
        s.input_finished()
        e = np.asarray(self.ex.compute(s), dtype=np.float32)
        return e / (np.linalg.norm(e) + 1e-9)


def guardar_huella(embs: list[np.ndarray], umbral: float, extra: dict | None = None) -> None:
    HUELLA.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(HUELLA.parent, 0o700)
    E = np.stack(embs)
    c = E.mean(0)
    meta = {"modelo": MODELO.name, "fecha": time.strftime("%Y-%m-%d %H:%M"), "n": len(embs), **(extra or {})}
    tmp = HUELLA.with_name(".voz.tmp.npz")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        np.savez(f, embs=E, centro=c / np.linalg.norm(c), umbral=np.float32(umbral), meta=json.dumps(meta))
    os.replace(tmp, HUELLA)
    os.chmod(HUELLA, 0o600)


class Verificador:
    def __init__(self, umbral: float | None = None):
        d = np.load(HUELLA)
        self.embs = d["embs"]
        self.centro = d["centro"]
        self.umbral = float(umbral if umbral is not None else d["umbral"])
        self.meta = json.loads(str(d["meta"]))
        self.ex = Extractor()

    def puntuacion(self, audio: np.ndarray) -> float:
        """Parecido con la huella: media entre el centro y las 3 tomas más parecidas (robusto a condiciones)."""
        e = self.ex(audio)
        top = np.sort(self.embs @ e)[-3:].mean()
        return float(0.5 * (self.centro @ e) + 0.5 * top)

    def es_el_senor(self, audio: np.ndarray) -> tuple[bool, float]:
        p = self.puntuacion(audio)
        return p >= self.umbral, p


def cargar(umbral: float | None = None) -> Verificador | None:
    if not HUELLA.exists():
        return None
    return Verificador(umbral)
