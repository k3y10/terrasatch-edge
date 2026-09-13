"""Validated receive targets. Discovery never grants RF transmission permission."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .radio_profiles import bca_frs_channel


def parse_frequency(value: str | int) -> int:
    """Parse integer Hz or a decimal with k/M/G and optional Hz suffix."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmMgG]?)(?:[hH][zZ])?", str(value).strip())
    if not match:
        raise ValueError("Use integer Hz or a frequency such as 462.650M / 462.650MHz")
    hz = Decimal(match[1]) * {"": 1, "k": 1000, "m": 1000000, "g": 1000000000}[match[2].lower()]
    if hz != hz.to_integral_value() or not 1 <= hz <= 6_000_000_000:
        raise ValueError("Frequency must be whole Hz between 1 and 6000000000")
    return int(hz)


class RepeaterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    provider: str = Field(default="manual", min_length=1, max_length=64)
    provider_id: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, max_length=200)
    output_frequency_hz: int = Field(strict=True, gt=0, le=6_000_000_000)
    input_frequency_hz: int | None = Field(default=None, strict=True, gt=0, le=6_000_000_000)
    offset_hz: int | None = Field(default=None, strict=True)
    location_text: str | None = Field(default=None, max_length=300)
    last_verified_at: str | None = Field(default=None, max_length=40)


class RadioTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$")
    name: str = Field(min_length=1, max_length=200)
    profile: str = Field(default="manual", min_length=1, max_length=64)
    source_type: Literal["manual", "profile", "repeater", "organization"] = "manual"
    frequency_hz: int = Field(strict=True, gt=0, le=6_000_000_000)
    modulation: Literal["nfm", "fm"] = "nfm"
    bandwidth_hz: int | None = Field(default=None, strict=True, ge=8000, le=48000)
    channel: int | None = Field(default=None, strict=True, ge=1, le=22)
    ctcss_hz: float | None = Field(default=None, ge=60, le=260)
    dcs_code: str | None = Field(default=None, pattern=r"^[0-7]{3}[NI]?$", max_length=4)
    repeater: RepeaterMetadata | None = None
    enabled: bool = Field(default=True, strict=True)
    priority: int = Field(default=0, strict=True, ge=0, le=100)
    discovered: bool = Field(default=False, strict=True)
    transmit_authorized: Literal[False] = False

    @model_validator(mode="after")
    def coherent_target(self) -> RadioTarget:
        if self.channel is not None:
            if self.profile != "bca-frs-na" or bca_frs_channel(self.channel).frequency_hz != self.frequency_hz:
                raise ValueError("BCA channel/profile/frequency must agree")
        if self.profile == "bca-frs-na" and self.channel is None:
            raise ValueError("BCA profile requires a channel")
        if self.repeater and self.repeater.output_frequency_hz != self.frequency_hz:
            raise ValueError("Repeater RX target must select its output frequency")
        return self

    @property
    def frequency_mhz(self) -> float:
        return self.frequency_hz / 1_000_000

    @property
    def display_name(self) -> str:
        return self.name

    def rf_metadata(self) -> dict:
        return {"radio_profile": self.profile, **self.model_dump(include={
            "frequency_hz", "modulation", "source_type", "channel", "ctcss_hz", "dcs_code", "repeater"
        }, exclude_none=True), "target_id": self.id, "target_name": self.name}


def bca_target(channel: int) -> RadioTarget:
    profile = bca_frs_channel(channel)
    return RadioTarget(id=f"bca-ch{profile.channel:02d}", name=profile.display_name,
                       profile=profile.profile, source_type="profile",
                       channel=profile.channel, frequency_hz=profile.frequency_hz)


def direct_target(frequency: str | int, modulation: str = "nfm") -> RadioTarget:
    hz = parse_frequency(frequency)
    return RadioTarget(id=f"frequency-{hz}-{modulation}", name=f"{hz / 1_000_000:.6f} MHz",
                       frequency_hz=hz, modulation=modulation.lower())


def validate_rtl_target(target: RadioTarget) -> None:
    # NESDR SMArt v5 R820T2 normal tuner path; direct sampling is not enabled.
    if not 25_000_000 <= target.frequency_hz <= 1_750_000_000:
        raise ValueError("RTL/NESDR receiver supports 25-1750 MHz in this normal tuner runtime")
    if not target.enabled:
        raise ValueError("Receive target is disabled")
