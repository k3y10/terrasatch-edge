from __future__ import annotations

import signal
import time
from dataclasses import dataclass

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import load_api_key, load_config
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
        try:
            self.client.health()
            return True, f"API online; {len(snapshot.devices)} local device records"
        except TerraSatchApiError as exc:
            return False, f"API unavailable; snapshot saved locally: {exc}"

    def run_forever(self, on_tick=None) -> None:  # type: ignore[no-untyped-def]
        signal.signal(signal.SIGINT, self.stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self.stop)

        while self.state.running:
            ok, message = self.tick()
            if on_tick is not None:
                on_tick(ok, message)
            deadline = time.monotonic() + self.config.scan_interval_seconds
            while self.state.running and time.monotonic() < deadline:
                time.sleep(0.25)
