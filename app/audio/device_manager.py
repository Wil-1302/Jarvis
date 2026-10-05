"""Descubrimiento y validación de dispositivos de audio (sounddevice / PortAudio).

En Windows cada dispositivo físico aparece una vez por host API (MME, DirectSound,
WASAPI, WDM-KS). Por defecto se trabaja con MME: Windows convierte el sample rate,
así que se puede capturar directamente a 16 kHz, que es lo que esperan los modelos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import sounddevice as sd

Kind = Literal["input", "output"]


class AudioDeviceError(Exception):
    """No se encontró el dispositivo o no admite la configuración pedida."""


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    host_api: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool = False
    is_default_output: bool = False

    def channels(self, kind: Kind) -> int:
        return self.max_input_channels if kind == "input" else self.max_output_channels


def _host_api_index(host_api: str) -> int:
    for index, api in enumerate(sd.query_hostapis()):
        if api["name"].lower() == host_api.lower():
            return index
    names = ", ".join(api["name"] for api in sd.query_hostapis())
    raise AudioDeviceError(f"Host API '{host_api}' no disponible (hay: {names})")


def list_devices(kind: Kind, host_api: str = "MME") -> list[AudioDevice]:
    api_index = _host_api_index(host_api)
    api = sd.query_hostapis(api_index)
    devices = []
    for index in api["devices"]:
        info = sd.query_devices(index)
        device = AudioDevice(
            index=index,
            name=info["name"],
            host_api=api["name"],
            max_input_channels=info["max_input_channels"],
            max_output_channels=info["max_output_channels"],
            default_samplerate=info["default_samplerate"],
            is_default_input=index == api["default_input_device"],
            is_default_output=index == api["default_output_device"],
        )
        if device.channels(kind) > 0:
            devices.append(device)
    return devices


def default_device(kind: Kind, host_api: str = "MME") -> AudioDevice:
    for device in list_devices(kind, host_api):
        if device.is_default_input if kind == "input" else device.is_default_output:
            return device
    raise AudioDeviceError(f"No hay dispositivo de {kind} predeterminado en {host_api}")


def find_device(kind: Kind, selector: str = "", host_api: str = "MME") -> AudioDevice:
    """Resuelve un dispositivo por índice, por parte de su nombre o el predeterminado."""
    selector = selector.strip()
    if not selector:
        return default_device(kind, host_api)
    devices = list_devices(kind, host_api)
    if selector.isdigit():
        for device in devices:
            if device.index == int(selector):
                return device
        raise AudioDeviceError(f"No existe el dispositivo de {kind} con índice {selector}")
    matches = [d for d in devices if selector.lower() in d.name.lower()]
    if not matches:
        raise AudioDeviceError(f"Ningún dispositivo de {kind} contiene '{selector}'")
    return matches[0]


def check_settings(device: AudioDevice, kind: Kind, samplerate: int, channels: int = 1) -> None:
    """Lanza AudioDeviceError si el dispositivo no admite esa configuración."""
    check = sd.check_input_settings if kind == "input" else sd.check_output_settings
    try:
        check(device=device.index, samplerate=samplerate, channels=channels, dtype="int16")
    except Exception as exc:  # PortAudioError / ValueError
        raise AudioDeviceError(
            f"{device.name}: no admite {samplerate} Hz / {channels} canal(es): {exc}"
        ) from exc


def supported_samplerates(
    device: AudioDevice, kind: Kind, candidates: tuple[int, ...] = (16000, 22050, 44100, 48000)
) -> list[int]:
    rates = []
    for rate in candidates:
        try:
            check_settings(device, kind, rate, 1)
            rates.append(rate)
        except AudioDeviceError:
            pass
    return rates
