"""Receive-only radio channel profiles for TerraSatch Edge."""

from __future__ import annotations

from dataclasses import dataclass

BCA_FRS_NA_PROFILE = "bca-frs-na"
BCA_PRIVACY_CODE_COUNT = 121

# North American FRS carrier frequencies used by BCA BC Link radios.
_BCA_FRS_FREQUENCIES_HZ: dict[int, int] = {
    1: 462_562_500,
    2: 462_587_500,
    3: 462_612_500,
    4: 462_637_500,
    5: 462_662_500,
    6: 462_687_500,
    7: 462_712_500,
    8: 467_562_500,
    9: 467_587_500,
    10: 467_612_500,
    11: 467_637_500,
    12: 467_662_500,
    13: 467_687_500,
    14: 467_712_500,
    15: 462_550_000,
    16: 462_575_000,
    17: 462_600_000,
    18: 462_625_000,
    19: 462_650_000,
    20: 462_675_000,
    21: 462_700_000,
    22: 462_725_000,
}


@dataclass(frozen=True)
class RadioChannelProfile:
    profile: str
    channel: int
    frequency_hz: int
    modulation: str = "fm"
    bandwidth_label: str = "narrowband"

    @property
    def frequency_mhz(self) -> float:
        return self.frequency_hz / 1_000_000

    @property
    def display_name(self) -> str:
        return f"BCA/FRS CH {self.channel} · {self.frequency_mhz:.4f} MHz"


def bca_frs_channel(channel: int) -> RadioChannelProfile:
    """Return the standard North American BCA/FRS carrier for channel 1-22."""

    try:
        frequency_hz = _BCA_FRS_FREQUENCIES_HZ[int(channel)]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("BCA/FRS channel must be between 1 and 22") from exc
    return RadioChannelProfile(
        profile=BCA_FRS_NA_PROFILE,
        channel=int(channel),
        frequency_hz=frequency_hz,
    )


def bca_frs_channels() -> list[RadioChannelProfile]:
    return [bca_frs_channel(channel) for channel in range(1, 23)]
