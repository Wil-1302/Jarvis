"""Compara modelos de faster-whisper en español: precisión (WER), latencia y VRAM.

    uv run python scripts/benchmark_stt.py [small medium large-v3-turbo]

El audio de prueba se genera localmente con las voces Piper configuradas y se le
añade ruido (SNR 20 dB). Es voz sintética: sirve para comparar modelos entre sí,
no como medida absoluta de la precisión con voz real.
"""

from __future__ import annotations

import gc
import re
import subprocess
import sys
import time
import unicodedata

import numpy as np

from app.audio.resample import resample
from app.brain.ollama_client import OllamaClient
from app.config.settings import load_settings
from app.voice.stt import SpeechToText
from app.voice.tts import TextToSpeech

PHRASES = [
    "Jarvis, abre Spotify y reproduce Arctic Monkeys.",
    "¿Cómo estás hoy?",
    "Dime hola.",
    "¿Qué hora es en Lima?",
    "Necesito crear un sistema de ventas con control de inventario.",
    "Sube el volumen al setenta por ciento.",
    "Busca en internet la documentación de FastAPI.",
    "Recuérdame comprar leche mañana a las ocho de la noche.",
]
VOICES = ["es_MX-ald-medium", "es_MX-claude-high"]


def normalize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", text).split()


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalize(reference), normalize(hypothesis)
    d = np.zeros((len(ref) + 1, len(hyp) + 1), dtype=int)
    d[:, 0] = np.arange(len(ref) + 1)
    d[0, :] = np.arange(len(hyp) + 1)
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + cost)
    return d[-1, -1] / max(len(ref), 1)


def vram_used_mib() -> int:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
    ).stdout
    return int(out.strip().splitlines()[0])


def build_dataset(settings) -> list[tuple[str, np.ndarray]]:
    rng = np.random.default_rng(0)
    data = []
    for voice in VOICES:
        tts = TextToSpeech(settings.models_path, voice)
        for phrase in PHRASES:
            speech = tts.synthesize(phrase)
            audio = resample(speech.audio, speech.sample_rate, 16000)
            noise = rng.normal(0, 1, audio.size).astype(np.float32)
            signal_power = np.mean(audio**2)
            audio = audio + noise * np.sqrt(signal_power / 10 ** (20 / 10))
            data.append((phrase, audio))
    return data


def main(models: list[str]) -> None:
    settings = load_settings()
    with OllamaClient(settings.ollama_host, timeout=120) as ollama:
        ollama.chat(settings.ollama_model, [{"role": "user", "content": "hola"}])
    print(f"Ollama ({settings.ollama_model}) cargado. VRAM usada: {vram_used_mib()} MiB")

    data = build_dataset(settings)
    print(f"{len(data)} frases de prueba generadas ({len(VOICES)} voces, SNR 20 dB)\n")

    rows = []
    for model in models:
        before = vram_used_mib()
        start = time.perf_counter()
        stt = SpeechToText(
            settings.models_path, model, settings.stt_device, settings.stt_compute_type
        )
        load_s = time.perf_counter() - start
        stt.warmup()
        vram = vram_used_mib() - before
        errors, times = [], []
        for phrase, audio in data:
            result = stt.transcribe(audio)
            errors.append(wer(phrase, result.text))
            times.append(result.elapsed)
            if errors[-1] > 0:
                print(f"  [{model}] '{phrase}' -> '{result.text}'")
        rows.append((model, stt.device, load_s, vram, np.mean(errors), np.mean(times), max(times)))
        del stt
        gc.collect()
        time.sleep(1)

    print(f"\n{'modelo':<16}{'device':<7}{'carga s':>8}{'VRAM MiB':>10}{'WER':>8}"
          f"{'media s':>9}{'máx s':>8}")
    for model, device, load_s, vram, err, mean_t, max_t in rows:
        print(f"{model:<16}{device:<7}{load_s:>8.1f}{vram:>10}{err:>8.1%}{mean_t:>9.3f}{max_t:>8.3f}")
    print(f"\nVRAM total usada al final: {vram_used_mib()} MiB")


if __name__ == "__main__":
    main(sys.argv[1:] or ["small", "medium", "large-v3-turbo"])
