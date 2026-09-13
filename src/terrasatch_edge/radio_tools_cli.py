"""Operator RX diagnostics and optional directory commands."""

import json
import signal
import threading
from typing import Annotated

import typer

from .radio_operation import radio_operation
from .config import get_paths, load_config
from .radio_calibration import probe_radio_noise
from .radio_service import load_resolved_radio_config
from .radio_targets import bca_target, direct_target, validate_rtl_target
from .repeater_directory import DirectoryCache, DiscoveryQuery, OpenRepeaterProvider


def register_radio_tools(app: typer.Typer):
    @app.command("targets")
    def targets():
        """List configured targets; discovery never adds targets automatically."""
        config = load_resolved_radio_config(load_config()).config
        items = config.targets or [bca_target(c) for c in config.receivers[0].channels]
        typer.echo(json.dumps([t.model_dump() for t in items], indent=2))

    @app.command("devices")
    def devices():
        """Show hardware inventory and actual runtime capabilities."""
        from .discovery import scan_hardware
        snapshot = scan_hardware(include_network=False)
        from .radio_rx_provider import RtlRxProvider
        devices = [d.model_dump(mode="json") for d in snapshot.devices if d.kind == "sdr"]
        typer.echo(json.dumps(dict(devices=devices, provider=RtlRxProvider().status()), indent=2))

    @app.command("probe")
    @radio_operation
    def probe(
        frequency: Annotated[str | None, typer.Option("--frequency")] = None,
        channel: Annotated[int | None, typer.Option("--channel", min=1, max=22)] = None,
        modulation: Annotated[str, typer.Option("--modulation")] = "nfm",
        seconds: Annotated[float, typer.Option("--seconds", min=0.5, max=60)] = 10,
    ):
        """Measure bounded PCM activity without STT, audio retention, or ingestion."""
        stop = threading.Event()
        previous = {}
        try:
            if frequency is not None and channel is not None:
                raise ValueError("Choose --frequency or --channel")
            edge = load_config()
            config = load_resolved_radio_config(edge).config
            if not config.enabled:
                raise ValueError("Radio reception is disabled by policy")
            target = direct_target(frequency, modulation) if frequency else bca_target(channel) if channel else config.selected_target()
            validate_rtl_target(target)
            from .radio_cli import _receive_settings
            settings = _receive_settings(edge, config, target=target,
                                         device_index=config.receivers[0].device_index)
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous[sig] = signal.signal(sig, lambda *_: stop.set())
            sample = probe_radio_noise(settings, probe_seconds=seconds, stop_event=stop)
            peak = max(sample.levels, default=0)
            typer.echo(json.dumps(dict(target=target.model_dump(), device_index=settings.device_index,
                                       requested_duration_seconds=seconds, cancelled=stop.is_set(),
                                       activity_detected=peak >= settings.activity_rms_threshold,
                                       audio_peak_rms=peak, pcm_floor_rms=sample.noise_floor_rms if sample.levels else None,
                                       calibration="configured squelch/gain; PCM floor is not RF RSSI/SNR",
                                       pcm_chunks=len(sample.levels)), indent=2))
        except (ValueError, RuntimeError) as exc:
            raise typer.BadParameter(str(exc)) from exc
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)

    @app.command("discover")
    def discover(
        radius: Annotated[float, typer.Option("--radius", min=1, max=500, help="Radius in km.")] = 75,
        mode: Annotated[str, typer.Option("--mode")] = "nfm",
        provider: Annotated[str, typer.Option("--provider")] = "open-repeater",
        limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 20,
        latitude: Annotated[float | None, typer.Option("--latitude", min=-90, max=90)] = None,
        longitude: Annotated[float | None, typer.Option("--longitude", min=-180, max=180)] = None,
        region: Annotated[str | None, typer.Option("--region")] = None,
    ):
        """Discover receive candidates; explicitly configure one before monitoring."""
        try:
            edge = load_config()
            source = "region" if region else "cli"
            if latitude is None and longitude is None and not region:
                location = edge.radio.get("location", {})
                if not isinstance(location, dict):
                    raise ValueError("radio.location must contain explicit site/receiver coordinates")
                latitude, longitude = location.get("latitude"), location.get("longitude")
                source = location.get("source", "receiver")
            query = DiscoveryQuery(latitude=latitude, longitude=longitude, radius=radius,
                                   region=region, mode=mode.lower(), limit=limit, location_source=source)
            if provider == "open-repeater":
                directory = OpenRepeaterProvider()
                result = DirectoryCache(get_paths().state_dir / "repeater-cache.sqlite3").search(directory, query)
            elif provider in {"manual", "organization"}:
                from .repeater_directory import ManualRepeaterProvider, OrganizationRepeaterProvider
                cls = ManualRepeaterProvider if provider == "manual" else OrganizationRepeaterProvider
                directory = cls(load_resolved_radio_config(edge).config.targets)
                result = dict(provider=provider, query=query.model_dump(), targets=[t.model_dump() for t in directory.search(query)])
            else:
                raise ValueError("Supported providers: open-repeater, manual, organization")
            typer.echo(json.dumps(result, indent=2))
        except (ValueError, RuntimeError, OSError) as exc:
            raise typer.BadParameter(str(exc)) from exc
