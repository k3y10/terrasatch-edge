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


class PairingStart(BaseModel):
    pairing_id: str
    device_code: str
    user_code: str
    verification_url: str
    expires_at: datetime
    interval_seconds: int = 5


class EdgeDevice(BaseModel):
    id: str
    organization_id: str
    site_id: str
    name: str
    hostname: str | None = None
    platform: str | None = None
    architecture: str | None = None
    agent_version: str | None = None
    hardware_inventory: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    remote_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    last_seen_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PairingClaim(BaseModel):
    status: str
    token: str | None = None
    device: EdgeDevice | None = None


class EdgeStatus(BaseModel):
    configured: bool
    api_url: str
    api_reachable: bool
    authenticated: bool
    site_id: str | None = None
    hostname: str
    device_count: int = 0
    details: dict[str, Any] = Field(default_factory=dict)
