from __future__ import annotations

import os

import numpy as np
import pytest

from app.audio import device_manager as dm
from app.audio.analysis import analyze
from app.audio.resample import resample, to_int16

HOSTAPIS = [
    {"name": "MME", "devices": [0, 1, 2], "default_input_device": 1, "default_output_device": 2},
    {"name": "Windows WASAPI", "devices": [3], "default_input_device": 3,
     "default_output_device": -1},
]
DEVICES = [
    {"name": "Asignador - Input", "max_input_channels": 2, "max_output_channels": 0,
     "default_samplerate": 44100.0},
    {"name": "Varios micrófonos (Realtek)", "max_input_channels": 2, "max_output_channels": 0,
     "default_samplerate": 44100.0},
    {"name": "Altavoces (Realtek)", "max_input_channels": 0, "max_output_channels": 2,
     "default_samplerate": 48000.0},
    {"name": "Micrófono WASAPI", "max_input_channels": 1, "max_output_channels": 0,
     "default_samplerate": 48000.0},
]


@pytest.fixture
def fake_sd(monkeypatch):
    def query_hostapis(index=None):
        return HOSTAPIS if index is None else HOSTAPIS[index]

    monkeypatch.setattr(dm.sd, "query_hostapis", query_hostapis)
    monkeypatch.setattr(dm.sd, "query_devices", lambda index: DEVICES[index])


def test_list_devices_by_kind(fake_sd) -> None:
    inputs = dm.list_devices("input")
    outputs = dm.list_devices("output")
    assert [d.index for d in inputs] == [0, 1]
    assert [d.index for d in outputs] == [2]
    assert inputs[1].is_default_input
    assert outputs[0].channels("output") == 2


def test_default_devices(fake_sd) -> None:
    assert dm.default_device("input").name.startswith("Varios micrófonos")
    assert dm.default_device("output").name == "Altavoces (Realtek)"


def test_find_device_by_index_name_or_default(fake_sd) -> None:
    assert dm.find_device("input", "0").index == 0
    assert dm.find_device("input", "realtek").index == 1
    assert dm.find_device("input", "").index == 1
    with pytest.raises(dm.AudioDeviceError):
        dm.find_device("input", "no-existe")
    with pytest.raises(dm.AudioDeviceError):
        dm.find_device("input", "9")


def test_unknown_host_api(fake_sd) -> None:
    with pytest.raises(dm.AudioDeviceError, match="ASIO"):
        dm.list_devices("input", "ASIO")


def test_no_default_output_in_host_api(fake_sd) -> None:
    with pytest.raises(dm.AudioDeviceError):
        dm.default_device("output", "Windows WASAPI")


def _sine(amplitude: float, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(16000 * seconds)) / 16000
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_analysis_of_speech_like_signal() -> None:
    audio = np.concatenate([np.zeros(8000, np.float32), _sine(0.3), np.zeros(8000, np.float32)])
    report = analyze(to_int16(audio), 16000)
    assert report.peak == pytest.approx(0.3, abs=0.01)
    assert report.rms_dbfs < report.peak_dbfs
    assert not report.clipping
    assert report.signal_detected


def test_analysis_of_silence() -> None:
    report = analyze(np.zeros(16000, np.int16), 16000)
    assert not report.signal_detected
    assert report.peak == 0


def test_analysis_detects_clipping() -> None:
    report = analyze(to_int16(np.clip(_sine(2.0), -1, 1)), 16000)
    assert report.clipping
    assert report.clipped_samples > 0


def test_analysis_of_empty_audio() -> None:
    assert analyze(np.zeros(0, np.int16), 16000).rms == 0


def test_resample_preserves_duration() -> None:
    audio = _sine(0.5, seconds=1.0)
    out = resample(audio, 16000, 22050)
    assert out.size == 22050
    assert resample(audio, 16000, 16000) is not None


@pytest.mark.hardware
def test_real_devices_are_listed() -> None:
    """Necesita una tarjeta de sonido; se omite si no hay dispositivos (p. ej. en CI)."""
    try:
        mic = dm.default_device("input")
        speakers = dm.default_device("output")
    except Exception as exc:
        pytest.skip(f"sin dispositivos de audio: {exc}")
    assert 16000 in dm.supported_samplerates(mic, "input")
    assert speakers.max_output_channels > 0


@pytest.mark.hardware
@pytest.mark.skipif(
    os.environ.get("JARVIS_HARDWARE_TESTS") != "1",
    reason="graba del micrófono; activar con JARVIS_HARDWARE_TESTS=1",
)
def test_real_microphone_records() -> None:
    from app.audio.stream import record

    audio = record(1.0, dm.default_device("input"))
    assert audio.size == 16000
    assert audio.dtype == np.int16
