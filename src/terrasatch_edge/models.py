from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class DeviceKind(StrEnum):
    SYSTEM = "system"
    USB = "usb"
    SERIAL = "serial"
    AUDIO = "audio"
    SDR = "sdr"
    GPS = "gps"
    NETWORK = "network"
    UNKNOWN = "unknown"


class HardwareDevice(BaseModel):
    kind: DeviceKind
    name: str
    identifier: str
    vendor: str | None = None
    product: str | None = None
    vendor_id: str | None = None
    product_id: str | None = None
    path: str | None = None
    status: str = "detected"
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemSnapshot(BaseModel):
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    hostname: str
    platform: str
    platform_release: str
    architecture: str
    python_version: str
    cpu_count_logical: int | None = None
    memory_total_bytes: int | None = None
    memory_available_bytes: int | None = None
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
    devices: list[HardwareDevice] = Field(default_factory=list)


class ApiIdentity(BaseModel):
    raw: dict[str, Any]


class SiteSummary(BaseModel):
    id: str
    name: str
    enabled: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)


class EdgeStatus(BaseModel):
    configured: bool
    api_url: str
    api_reachable: bool
    authenticated: bool
    site_id: str | None = None
    hostname: str
    device_count: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
