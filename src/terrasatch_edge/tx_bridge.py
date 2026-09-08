"""Explicit local provider executable, JSON stdin/stdout, never a remote shell command."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

from .radio_providers import RadioCapability, RadioProviderStatus, RadioReply


class ExternalRadioTxProvider:
    def __init__(self, executable: str) -> None:
        self.executable = Path(executable)
        if not self.executable.is_absolute() or not self.executable.is_file():
            raise ValueError("TX provider must be an installed absolute executable path")

    def _call(self, payload: dict, timeout: float) -> dict:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG"}
        }
        result = subprocess.run(
            [str(self.executable)],
            input=json.dumps({"protocol_version": 1, **payload}),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
            env=environment,
        )
        if len(result.stdout) > 16_384:
            raise ValueError("TX provider response exceeds protocol limit")
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or data.get("protocol_version") != 1:
            raise ValueError("Unsupported TX provider protocol")
        return data

    def status(self) -> RadioProviderStatus:
        data = self._call({"operation": "status"}, 5)
        capabilities = frozenset(RadioCapability(item) for item in data.get("capabilities", []))
        required = {RadioCapability.TRANSMIT, RadioCapability.PTT, RadioCapability.OUTPUT}
        duplex = capabilities & {RadioCapability.HALF_DUPLEX, RadioCapability.FULL_DUPLEX}
        ready = (
            data.get("ready") is True
            and required <= capabilities
            and len(duplex) == 1
            and data.get("rx_coordination") in ("independent", "managed")
            and data.get("watchdog") is True
        )
        if not isinstance(data.get("device_id"), str) or not data["device_id"]:
            ready = False
        return RadioProviderStatus(
            str(self.executable),
            data.get("device_id"),
            ready,
            capabilities,
            simulated=data.get("simulated") is not False,
        )

    def transmit(self, reply: RadioReply) -> None:
        data = self._call({"operation": "transmit", "reply": asdict(reply)}, reply.max_seconds + 5)
        if (
            data.get("command_id") != reply.command_id
            or data.get("status") != "transmitted"
            or data.get("ptt_released") is not True
            or data.get("rx_restored") is not True
        ):
            raise RuntimeError("Provider did not confirm transmission and PTT/RX cleanup")
