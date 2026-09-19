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
    def status(self, asset_id: str) -> AssetProviderStatus: ...

    def execute(self, mission: AssetMission) -> None: ...


def provider_capabilities(providers: dict[str, FieldAssetProvider] | None) -> set[str]:
    """Report only capabilities backed by a ready installed provider."""

    capabilities: set[str] = set()
    for provider in (providers or {}).values():
        try:
            status = provider.status("*")
        except Exception:
            continue
        if status.ready:
            capabilities.update(status.capabilities)
    return capabilities