"""Provider-neutral contracts for field assets controlled through TerraSatch Edge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AssetProviderStatus:
    name: str
    ready: bool
    capabilities: frozenset[str]


@dataclass(frozen=True)
class AssetMission:
    command_id: str
    mission_id: str
    asset_id: str
    mission_type: str
    objective: str
    target: dict[str, Any]
    parameters: dict[str, Any]


class FieldAssetProvider(Protocol):
    """Installed provider capable of executing typed field-asset missions."""

    def reported_capabilities(self) -> frozenset[str]: ...

    def status(self, asset_id: str) -> AssetProviderStatus: ...

    def execute(self, mission: AssetMission) -> None: ...


def provider_capabilities(providers: dict[str, FieldAssetProvider] | None) -> set[str]:
    """Report only capabilities explicitly backed by installed provider adapters."""

    capabilities: set[str] = set()
    for provider in (providers or {}).values():
        try:
            capabilities.update(
                capability
                for capability in provider.reported_capabilities()
                if isinstance(capability, str) and capability.strip()
            )
        except Exception:
            # One broken optional provider must not cause Edge to overstate capability
            # or take unrelated receive/heartbeat functions offline.
            continue
    return capabilities
