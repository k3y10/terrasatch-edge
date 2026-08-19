from __future__ import annotations

from dataclasses import dataclass

from .models import DeviceKind, HardwareDevice


@dataclass(frozen=True)
class AdapterRule:
    name: str
    terms: tuple[str, ...]
    kind: DeviceKind
    capabilities: tuple[str, ...]


RULES = (
    AdapterRule(
        name="RTL-SDR / Nooelec",
        terms=("rtl283", "rtl-sdr", "nooelec", "nesdr", "realtek 2838"),
        kind=DeviceKind.SDR,
        capabilities=(
            "iq_stream",
            "fm_demodulation",
            "rtl-sdr",
            "nooelec",
        ),
    ),
    AdapterRule(
        name="HackRF",
        terms=("hackrf",),
        kind=DeviceKind.SDR,
        capabilities=(
            "hardware:hackrf",
            "hackrf",
        ),
    ),
    AdapterRule(
        name="GPS / NMEA",
        terms=("gps", "gnss", "nmea", "u-blox", "ublox"),
        kind=DeviceKind.GPS,
        capabilities=("position", "time"),
    ),
    AdapterRule(
        name="USB Audio",
        terms=("usb audio", "c-media", "cm108", "cm119"),
        kind=DeviceKind.AUDIO,
        capabilities=("audio_input",),
    ),
)


def classify_device(device: HardwareDevice) -> HardwareDevice:
    haystack = " ".join(
        value
        for value in (
            device.name,
            device.identifier,
            device.vendor or "",
            device.product or "",
            device.path or "",
        )
        if value
    ).lower()

    for rule in RULES:
        if any(term in haystack for term in rule.terms):
            return device.model_copy(
                update={
                    "kind": rule.kind,
                    "capabilities": sorted(set(device.capabilities) | set(rule.capabilities)),
                    "metadata": {**device.metadata, "adapter": rule.name},
                }
            )
    return device
