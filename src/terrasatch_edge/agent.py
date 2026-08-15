from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from typing import Callable

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import load_api_key, load_config, save_remote_config
from .discovery import save_snapshot, scan_hardware


@dataclass
class AgentState:
    running: bool = True


class EdgeAgent:
    def __init__(self) -> None:
        self.config = load_config()
        self.api_key = load_api_key()
        self.client = TerraSatchApiClient(self.config.api_url, self.api_key)
        self.state = AgentState()

    def stop(self, *_args: object) -> None:
        self.state.running = False

    def tick(self) -> tuple[bool, str]:
        snapshot = scan_hardware(include_network=True)
        save_snapshot(snapshot)
        if not self.api_key:
            try:
                self.client.health()
                return False, "API online; Edge is not paired yet"
            except TerraSatchApiError as exc:
                return False, f"API unavailable; snapshot saved locally: {exc}"

        try:
            heartbeat = self.client.heartbeat(snapshot)
            remote_config = self.client.remote_config()
            save_remote_config(remote_config)
            device = heartbeat.get("device") if isinstance(heartbeat, dict) else None
            device_name = device.get("name") if isinstance(device, dict) else self.config.node_name
            return (
                True,
                f"Edge online as {device_name or self.config.node_name or snapshot.hostname}; "
                f"{len(snapshot.devices)} hardware records synced",
            )
        except TerraSatchApiError as exc:
            return False, f"Edge heartbeat failed; snapshot retained locally: {exc}"

    def run_forever(
        self,
        on_tick: Callable[[bool, str], None] | None = None,
        *,
        install_signal_handlers: bool = True,
    ) -> None:
        if install_signal_handlers:
            try:
                signal.signal(signal.SIGINT, self.stop)
                if hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, self.stop)
            except ValueError:
                pass

        while self.state.running:
            ok, message = self.tick()
            if on_tick is not None:
                on_tick(ok, message)
            deadline = time.monotonic() + self.config.scan_interval_seconds
            while self.state.running and time.monotonic() < deadline:
                time.sleep(0.25)
