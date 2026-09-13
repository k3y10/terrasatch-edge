"""Receive-only provider boundary, independent of TX provider capabilities."""

from typing import Protocol

from .radio_receiver import ContinuousRtlReceiver, RadioReceiveSettings
from .radio_targets import RadioTarget, validate_rtl_target
from .tooling import find_executable


class ReceiverProvider(Protocol):
    def status(self) -> dict: ...
    def validate(self, target: RadioTarget) -> None: ...
    def receiver(self, settings: RadioReceiveSettings, **kwargs): ...


class RtlRxProvider:
    def status(self) -> dict:
        runtime = {name: str(path) if (path := find_executable(name)) else None
                   for name in ("rtl_fm", "rtl_sdr", "rtl_test")}
        ready = all(runtime.values())
        return dict(provider="rtl-sdr", runtime_ready=ready, tools=runtime,
                    capabilities=["radio:receive", "audio:capture"] if ready else [])

    def validate(self, target: RadioTarget) -> None:
        validate_rtl_target(target)

    def receiver(self, settings: RadioReceiveSettings, **kwargs):
        self.validate(settings.profile)
        return ContinuousRtlReceiver(settings, **kwargs)
