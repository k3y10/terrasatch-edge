"""Provider operations are independent of USB discovery and control-plane policy.

A hardware adapter must implement these operations before reporting their capability.
The bundled provider is simulation only; it cannot generate audio, assert PTT, or RF.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class RadioCapability(StrEnum):
    RECEIVE = "radio:receive"
    TRANSMIT = "radio:transmit"
    PTT = "radio:ptt"
    HALF_DUPLEX = "radio:half_duplex"
    FULL_DUPLEX = "radio:full_duplex"
    CAPTURE = "audio:capture"
    OUTPUT = "audio:output"


@dataclass(frozen=True)
class RadioProviderStatus:
    provider_id: str
    device_id: str | None
    ready: bool
    capabilities: frozenset[RadioCapability]
    simulated: bool = False

    def reported_capabilities(self) -> set[str]:
        if not self.ready or self.simulated:
            return set()
        return {cap.value for cap in self.capabilities}


@dataclass(frozen=True)
class RadioReply:
    command_id: str
    text: str
    logical_channel_id: str
    provider_channel: str
    frequency_hz: int
    max_seconds: float


class RadioTxProvider(Protocol):
    """A real adapter must enforce duration, PTT cleanup and duplex coordination.

    Separate RX and TX device IDs are valid. A half-duplex adapter owns pausing RX
    before asserting PTT, deasserting PTT in finally, and restoring RX. Implementations
    must persist command IDs before effects and never repeat an uncertain transmission.
    """

    def status(self) -> RadioProviderStatus: ...
    def transmit(self, reply: RadioReply) -> None: ...


class SimulationRadioProvider:
    def status(self) -> RadioProviderStatus:
        return RadioProviderStatus("simulation", None, True, frozenset(), simulated=True)

    def simulate(self) -> tuple[str, str]:
        return "simulated", "Simulation-only radio reply accepted; no RF/PTT operation was attempted"


def rf_execution_blocker() -> str:
    return (
        "RF execution unavailable: current API result contract accepts only simulated/failed; "
        "a compatible TX adapter and transmitted-result support are required; no RF/PTT operation performed"
    )
