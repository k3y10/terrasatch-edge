"""Receive-only BCA/FRS CLI commands for TerraSatch Edge."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import EdgeConfig, get_paths, load_api_key, load_config
from .ingest import ingest_audio_file
from .radio_calibration import RadioCalibrationError, RadioCalibrationResult, auto_calibrate_radio
from .radio_profiles import (
    BCA_FRS_NA_PROFILE,
    BCA_PRIVACY_CODE_COUNT,
    bca_frs_channel,
    bca_frs_channels,
)
from .radio_receiver import RadioReceiveError, RadioReceiveSettings, capture_one_transmission
from .radio_service import (
    RadioMonitorConfig,
    RadioMonitorService,
    load_resolved_radio_config,
    read_radio_status,
    request_radio_stop,
)
from .speech import FasterWhisperSpeechProvider, SpeechProcessingError, SpeechProviderUnavailable

console = Console()


def _receive_settings(
    edge_config: EdgeConfig,
    monitor_config: RadioMonitorConfig,
    *,
    channel: int,
    device_index: int = 0,
) -> RadioReceiveSettings:
    processing = monitor_config.processing
    return RadioReceiveSettings(
        channel=channel,
        device_index=device_index,
        output_sample_rate=edge_config.radio_output_sample_rate,
        demod_sample_rate=edge_config.radio_demod_sample_rate,
        rtl_squelch=edge_config.radio_squelch,
        rtl_squelch_delay=edge_config.radio_squelch_delay,
        gain_db=edge_config.radio_gain_db,
        read_chunk_seconds=edge_config.radio_chunk_seconds,
        end_gap_seconds=processing.end_gap_seconds,
        min_transmission_seconds=processing.min_transmission_seconds,
        max_transmission_seconds=processing.max_transmission_seconds,
        activity_rms_threshold=processing.min_peak_rms,
        release_rms_threshold=processing.release_rms_threshold,
    )


def _print_calibration(result: RadioCalibrationResult) -> None:
    gain = "tuner auto" if result.settings.gain_db is None else f"{result.settings.gain_db:g} dB"
    console.print(
        "[green]✓ RF calibrated[/green] · "
        f"gain {gain} · squelch {result.settings.rtl_squelch} · "
        f"noise RMS {result.noise_floor_rms} · "
        f"gate {result.activity_rms_threshold}/{result.release_rms_threshold} · "
        f"{result.attempts} probe(s)"
    )


def _radio_source(base_source: str, channel: int) -> str:
    """Keep BCA channel provenance inside the API's 64-character source field."""

    suffix = f"-radio-bca-ch{channel:02d}"
    prefix = (base_source or "terrasatch-edge").strip() or "terrasatch-edge"
    maximum_prefix = max(1, 64 - len(suffix))
    prefix = prefix[:maximum_prefix].rstrip("-_") or "edge"
    return f"{prefix}{suffix}"


def _capture_path(channel: int) -> Path:
    root = get_paths().state_dir / "radio-captures"
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return root / f"bca-ch{channel:02d}-{stamp}-{uuid.uuid4().hex[:8]}.wav"


def register_radio_commands(app: typer.Typer) -> None:
    """Attach BCA/FRS receive commands to the native Edge Typer app."""

    radio_app = typer.Typer(no_args_is_help=True, help="Persistent TerraSatch radio monitor.")
    app.add_typer(radio_app, name="radio")

    @radio_app.command("start")
    def radio_start(
        channel: Annotated[
            int | None,
            typer.Option("--channel", "-c", min=1, max=22, help="BCA/FRS channel 1-22."),
        ] = None,
        privacy_code: Annotated[
            int | None,
            typer.Option("--privacy-code", min=0, max=BCA_PRIVACY_CODE_COUNT),
        ] = None,
        callsign: Annotated[str | None, typer.Option("--callsign")] = None,
        hotwords: Annotated[
            str | None,
            typer.Option("--hotwords", help="Local names and terminology to bias transcription."),
        ] = None,
        squelch: Annotated[
            int | None,
            typer.Option("--squelch", min=1, max=100, help="rtl_fm squelch threshold."),
        ] = None,
        gain_db: Annotated[
            float | None,
            typer.Option("--gain-db", min=0, max=60, help="Optional fixed RTL-SDR gain."),
        ] = None,
        auto_calibrate: Annotated[
            bool,
            typer.Option(
                "--auto-calibrate/--no-auto-calibrate",
                help="Measure the local RF floor and choose gain, squelch, and PCM gates.",
            ),
        ] = True,
    ) -> None:
        """Continuously receive while transcription and API delivery run independently."""

        edge_config = load_config()
        key = load_api_key()
        if not key:
            console.print("[red]No Edge credential configured. Run `terrasatch-edge setup`.[/red]")
            raise typer.Exit(2)
        if not edge_config.site_id:
            console.print("[red]No paired site is configured.[/red]")
            raise typer.Exit(2)
        if squelch is not None or gain_db is not None:
            edge_config = edge_config.model_copy(
                update={
                    "radio_squelch": squelch or edge_config.radio_squelch,
                    "radio_gain_db": gain_db if gain_db is not None else edge_config.radio_gain_db,
                }
            )
        resolved = load_resolved_radio_config(edge_config)
        monitor_config = resolved.config
        receiver = monitor_config.receivers[0]
        if channel is not None or privacy_code is not None:
            receiver = receiver.model_copy(
                update={
                    "channels": [channel or receiver.channels[0]],
                    "privacy_code": (
                        privacy_code if privacy_code is not None else receiver.privacy_code
                    ),
                }
            )
            monitor_config = monitor_config.model_copy(
                update={"receivers": [receiver, *monitor_config.receivers[1:]]}
            )
        for warning in resolved.warnings:
            console.print(f"[yellow]! {warning}[/yellow]")
        if monitor_config.profile != BCA_FRS_NA_PROFILE:
            console.print(
                f"[red]Continuous vNext currently supports '{BCA_FRS_NA_PROFILE}', "
                f"not '{monitor_config.profile}'.[/red]"
            )
            raise typer.Exit(2)
        calibration: RadioCalibrationResult | None = None
        if auto_calibrate and monitor_config.processing.auto_calibrate:
            console.print(
                f"[cyan]Calibrating RF environment[/cyan] for channel {receiver.channels[0]}..."
            )
            try:
                calibration = auto_calibrate_radio(
                    _receive_settings(
                        edge_config,
                        monitor_config,
                        channel=receiver.channels[0],
                        device_index=receiver.device_index,
                    ),
                    fixed_squelch=squelch,
                    fixed_gain_db=gain_db,
                    probe_seconds=monitor_config.processing.calibration_seconds,
                )
            except RadioCalibrationError as exc:
                console.print(f"[red]Radio auto-calibration failed:[/red] {exc}")
                raise typer.Exit(3) from exc
            edge_config = edge_config.model_copy(
                update={
                    "radio_squelch": calibration.settings.rtl_squelch,
                    "radio_gain_db": calibration.settings.gain_db,
                }
            )
            processing = monitor_config.processing.model_copy(
                update={
                    "min_peak_rms": calibration.activity_rms_threshold,
                    "release_rms_threshold": calibration.release_rms_threshold,
                }
            )
            monitor_config = monitor_config.model_copy(update={"processing": processing})
            _print_calibration(calibration)
        else:
            console.print(
                "[yellow]RF auto-calibration disabled[/yellow] · "
                f"squelch {edge_config.radio_squelch} · "
                f"gate {monitor_config.processing.min_peak_rms}/"
                f"{monitor_config.processing.release_rms_threshold}"
            )
        provider = FasterWhisperSpeechProvider(
            model_name=edge_config.speech_model,
            device=edge_config.speech_device,
            compute_type=edge_config.speech_compute_type,
            vad_filter=edge_config.speech_vad_filter,
            local_files_only=edge_config.speech_local_files_only,
        )
        service = RadioMonitorService(
            edge_config=edge_config,
            monitor_config=monitor_config,
            provider=provider,
            client=TerraSatchApiClient(edge_config.api_url, key),
            callsign=callsign,
            hotwords=hotwords,
            calibration=calibration,
        )
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        profile = bca_frs_channel(service.channel)
        console.print("[bold green]TerraSatch Radio Monitor[/bold green]")
        console.print(
            f"Continuous receive-only monitoring on channel {profile.channel} "
            f"({profile.frequency_mhz:.4f} MHz). Press Ctrl+C to stop."
        )
        if receiver.privacy_code is not None:
            console.print(
                f"[yellow]Privacy code {receiver.privacy_code} is configured context only; "
                "no CTCSS/DCS detection is claimed.[/yellow]"
            )
        try:
            service.run_forever()
        except (RadioReceiveError, RuntimeError) as exc:
            console.print(f"[red]Radio monitor failed:[/red] {exc}")
            raise typer.Exit(3) from exc

    @radio_app.command("status")
    def radio_status(
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Show receiver health, filtering counters, and durable queue depth."""

        status = read_radio_status()
        if json_output:
            console.print_json(json.dumps(status, default=str))
            return
        console.print("[bold]TerraSatch Radio Monitor[/bold]")
        console.print(f"State: [bold]{status.get('receiver_state', 'UNKNOWN')}[/bold]")
        console.print(f"Receiver: {status.get('receiver', 'not started')}")
        console.print(f"Profile: {status.get('profile', BCA_FRS_NA_PROFILE)}")
        if status.get("channel"):
            console.print(f"Channel: {status['channel']}")
        if status.get("frequency_hz"):
            console.print(f"Frequency: {int(status['frequency_hz']) / 1_000_000:.4f} MHz")
        console.print("")
        console.print(f"RF candidates:      {status.get('rf_candidates', 0)}")
        console.print(f"Accepted:           {status.get('accepted', 0)}")
        console.print(f"No speech:          {status.get('no_speech_rejected', 0)}")
        rejected = int(status.get("short_rejected", 0)) + int(status.get("signal_rejected", 0))
        console.print(f"Noise/short:         {rejected}")
        console.print("")
        console.print(f"API: {status.get('api_status', 'UNKNOWN')}")
        console.print(f"Outbox: {status.get('outbox_depth', 0)}")
        console.print(f"Audio retention: {status.get('audio_retention', 'OFF')}")
        if status.get("noise_floor_rms") is not None:
            gain = status.get("gain_db")
            gain_label = "auto" if gain is None else f"{gain:g} dB"
            console.print(
                "RF calibration: "
                f"{status.get('calibration_mode', 'manual')} · "
                f"noise RMS {status['noise_floor_rms']} · "
                f"gate {status.get('activity_rms_threshold')}/"
                f"{status.get('release_rms_threshold')} · "
                f"gain {gain_label} · squelch {status.get('squelch')}"
            )
        if status.get("last_error"):
            console.print(f"[yellow]Last issue: {status['last_error']}[/yellow]")

    @radio_app.command("stop")
    def radio_stop() -> None:
        """Request a foreground monitor in another terminal to stop gracefully."""

        path = request_radio_stop()
        console.print(
            f"[green]Stop requested.[/green] The receiver will close gracefully. ({path})"
        )

    @app.command("radio-channels")
    def radio_channels() -> None:
        """Show the North American BCA/FRS receive channel table."""

        table = Table(title="BCA / North American FRS receive channels")
        table.add_column("Channel", justify="right")
        table.add_column("Frequency")
        table.add_column("Mode")
        for profile in bca_frs_channels():
            table.add_row(str(profile.channel), f"{profile.frequency_mhz:.4f} MHz", "FM receive")
        console.print(table)
        console.print(
            "[dim]Privacy/sub-channel codes do not change the carrier. "
            "The v0.2.3 pilot listens channel-wide and does not yet filter CTCSS/DCS.[/dim]"
        )

    @app.command("listen-radio")
    def listen_radio(
        channel: Annotated[
            int | None,
            typer.Option("--channel", "-c", min=1, max=22, help="BCA/FRS channel 1-22."),
        ] = None,
        privacy_code: Annotated[
            int,
            typer.Option(
                "--privacy-code",
                min=0,
                max=BCA_PRIVACY_CODE_COUNT,
                help="BCA privacy code label (0-121); receive filtering is not enabled yet.",
            ),
        ] = 0,
        callsign: Annotated[str | None, typer.Option("--callsign")] = None,
        hotwords: Annotated[
            str | None,
            typer.Option(
                "--hotwords", help="Optional local names/callsigns to bias transcription."
            ),
        ] = None,
        once: Annotated[
            bool,
            typer.Option("--once", help="Capture, transcribe and ingest one call, then exit."),
        ] = False,
        keep_audio: Annotated[
            bool,
            typer.Option("--keep-audio", help="Keep successful capture WAV files for QA."),
        ] = False,
        wait_timeout: Annotated[
            float | None,
            typer.Option(
                "--wait-timeout",
                min=1,
                help="Seconds to wait for a carrier-gated call before returning an error.",
            ),
        ] = None,
        squelch: Annotated[
            int | None,
            typer.Option("--squelch", min=1, max=100, help="rtl_fm squelch threshold."),
        ] = None,
        gain_db: Annotated[
            float | None,
            typer.Option("--gain-db", min=0, max=60, help="Optional fixed RTL-SDR gain in dB."),
        ] = None,
        auto_calibrate: Annotated[
            bool,
            typer.Option(
                "--auto-calibrate/--no-auto-calibrate",
                help="Measure the local RF floor before listening.",
            ),
        ] = True,
    ) -> None:
        """Receive BCA radio traffic through Nooelec/RTL-SDR and ingest it into TerraSatch."""

        config = load_config()
        if config.radio_profile != BCA_FRS_NA_PROFILE:
            console.print(
                f"[red]Unsupported radio profile '{config.radio_profile}'. "
                f"The pilot requires '{BCA_FRS_NA_PROFILE}'.[/red]"
            )
            raise typer.Exit(2)

        selected_channel = channel or config.radio_channel
        if selected_channel is None:
            console.print("[red]Choose --channel 1-22 or set TERRASATCH_EDGE_RADIO_CHANNEL.[/red]")
            raise typer.Exit(2)

        profile = bca_frs_channel(selected_channel)
        key = load_api_key()
        if not key:
            console.print("[red]No Edge credential configured. Run `terrasatch-edge setup`.[/red]")
            raise typer.Exit(2)
        if not config.site_id:
            console.print("[red]No site assigned. Pair Edge again before radio ingestion.[/red]")
            raise typer.Exit(2)

        provider = FasterWhisperSpeechProvider(
            model_name=config.speech_model,
            device=config.speech_device,
            compute_type=config.speech_compute_type,
            vad_filter=config.speech_vad_filter,
            local_files_only=config.speech_local_files_only,
        )
        client = TerraSatchApiClient(config.api_url, key)
        settings = RadioReceiveSettings(
            channel=selected_channel,
            output_sample_rate=config.radio_output_sample_rate,
            demod_sample_rate=config.radio_demod_sample_rate,
            rtl_squelch=squelch if squelch is not None else config.radio_squelch,
            rtl_squelch_delay=config.radio_squelch_delay,
            gain_db=gain_db if gain_db is not None else config.radio_gain_db,
            read_chunk_seconds=config.radio_chunk_seconds,
            end_gap_seconds=config.radio_silence_seconds,
            min_transmission_seconds=config.radio_min_transmission_seconds,
            max_transmission_seconds=config.radio_max_transmission_seconds,
            activity_rms_threshold=config.radio_min_peak_rms,
            release_rms_threshold=config.radio_release_rms_threshold,
        )

        if auto_calibrate and config.radio_auto_calibrate:
            console.print(f"[cyan]Calibrating RF environment[/cyan] for {profile.display_name}...")
            try:
                calibration = auto_calibrate_radio(
                    settings,
                    fixed_squelch=squelch,
                    fixed_gain_db=gain_db,
                    probe_seconds=config.radio_calibration_seconds,
                )
            except RadioCalibrationError as exc:
                console.print(f"[red]Radio auto-calibration failed:[/red] {exc}")
                raise typer.Exit(3) from exc
            settings = calibration.settings
            _print_calibration(calibration)
        else:
            console.print(
                "[yellow]RF auto-calibration disabled[/yellow] · "
                f"squelch {settings.rtl_squelch} · "
                f"gate {settings.activity_rms_threshold}/{settings.release_rms_threshold}"
            )

        console.print(
            f"[green]Listening[/green] {profile.display_name} with Nooelec/RTL-SDR receive only."
        )
        if privacy_code:
            console.print(
                f"[yellow]Privacy code {privacy_code} is context-only in this pilot; "
                "Edge currently receives the full selected carrier.[/yellow]"
            )
        if not once:
            console.print(
                "[dim]Sequential pilot mode: receiver pauses while each call is transcribed/ingested.[/dim]"
            )

        while True:
            capture_path = _capture_path(selected_channel)
            try:
                capture = capture_one_transmission(
                    settings,
                    output_path=capture_path,
                    wait_timeout_seconds=wait_timeout,
                )
            except RadioReceiveError as exc:
                console.print(f"[red]Radio receive failed:[/red] {exc}")
                raise typer.Exit(3) from exc

            message_id = capture.source_message_id
            if privacy_code:
                message_id = f"{message_id}-p{privacy_code:03d}"
            source = _radio_source(config.source, selected_channel)
            console.print(
                f"[green]✓ Captured[/green] {capture.duration_seconds:.2f}s · "
                f"peak RMS {capture.peak_rms} · {capture.path}"
            )

            try:
                result = ingest_audio_file(
                    client=client,
                    config=config,
                    provider=provider,
                    audio_path=capture.path,
                    callsign=callsign,
                    source_message_id=message_id,
                    source=source,
                    hotwords=hotwords,
                    initial_prompt=(
                        "TerraSatch field radio traffic. Avalanche and mountain operations terminology."
                    ),
                    started_at=capture.started_at,
                    ended_at=capture.ended_at,
                    rf_metadata={
                        "receiver_device_id": config.device_id,
                        "receiver_name": config.node_name,
                        "sdr_index": 0,
                        "sdr_serial": None,
                        "radio_profile": config.radio_profile,
                        "channel": selected_channel,
                        "frequency_hz": profile.frequency_hz,
                        "privacy_code": privacy_code or None,
                        "privacy_code_source": "configured" if privacy_code else None,
                        "ctcss_hz": None,
                        "tone_detected": False,
                        "peak_rms": capture.peak_rms,
                        "signal_dbfs": None,
                        "snr_db": None,
                        "duration_ms": capture.duration_ms,
                    },
                )
            except (
                SpeechProviderUnavailable,
                SpeechProcessingError,
                TerraSatchApiError,
                ValueError,
            ) as exc:
                console.print(f"[red]Radio audio ingestion failed:[/red] {exc}")
                console.print(f"[yellow]Captured WAV retained for QA:[/yellow] {capture.path}")
                raise typer.Exit(4) from exc

            console.print("[green]✓ Radio transmission transcribed and accepted[/green]")
            console.print(f"Transcript: [bold]{result.transcript.normalized_text}[/bold]")
            console.print(f"Source: {source}")
            console.print_json(json.dumps(result.api_response, default=str))

            if not keep_audio:
                try:
                    capture.path.unlink()
                except OSError:
                    pass
            else:
                console.print(f"[dim]Capture retained: {capture.path}[/dim]")

            if once:
                return
