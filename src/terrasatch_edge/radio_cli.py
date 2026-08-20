"""Receive-only BCA/FRS CLI commands for TerraSatch Edge."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import get_paths, load_api_key, load_config
from .ingest import ingest_audio_file
from .radio_calibration import RadioCalibrationError, auto_calibrate_radio
from .radio_profiles import (
    BCA_FRS_NA_PROFILE,
    BCA_PRIVACY_CODE_COUNT,
    bca_frs_channel,
    bca_frs_channels,
)
from .radio_receiver import RadioReceiveError, RadioReceiveSettings, capture_one_transmission
from .speech import FasterWhisperSpeechProvider, SpeechProcessingError, SpeechProviderUnavailable

console = Console()


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


def _gain_label(gain_db: float | None) -> str:
    return "tuner auto" if gain_db is None else f"{gain_db:g} dB"


def register_radio_commands(app: typer.Typer) -> None:
    """Attach BCA/FRS receive commands to the native Edge Typer app."""

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
            typer.Option("--hotwords", help="Optional local names/callsigns to bias transcription."),
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
        auto_calibrate: Annotated[
            bool,
            typer.Option(
                "--auto-calibrate/--no-auto-calibrate",
                help="Automatically learn a quiet RF gain/squelch baseline before listening.",
            ),
        ] = True,
        squelch: Annotated[
            int | None,
            typer.Option(
                "--squelch",
                min=1,
                max=100,
                help="Advanced squelch override; auto-calibration chooses this by default.",
            ),
        ] = None,
        gain_db: Annotated[
            float | None,
            typer.Option(
                "--gain-db",
                min=0,
                max=60,
                help="Advanced tuner-gain override; auto-calibration chooses this by default.",
            ),
        ] = None,
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

        base_settings = RadioReceiveSettings(
            channel=selected_channel,
            output_sample_rate=config.radio_output_sample_rate,
            demod_sample_rate=config.radio_demod_sample_rate,
            rtl_squelch=config.radio_squelch,
            rtl_squelch_delay=config.radio_squelch_delay,
            gain_db=config.radio_gain_db,
            read_chunk_seconds=config.radio_chunk_seconds,
            end_gap_seconds=config.radio_silence_seconds,
            min_transmission_seconds=config.radio_min_transmission_seconds,
            max_transmission_seconds=config.radio_max_transmission_seconds,
        )

        if auto_calibrate:
            if squelch is None or gain_db is None:
                console.print(
                    f"[cyan]Calibrating RF environment[/cyan] for {profile.display_name}..."
                )
            try:
                calibration = auto_calibrate_radio(
                    base_settings,
                    fixed_squelch=squelch,
                    fixed_gain_db=gain_db,
                )
            except RadioCalibrationError as exc:
                console.print(f"[red]Radio auto-calibration failed:[/red] {exc}")
                console.print(
                    "[dim]For diagnostics you can temporarily supply --squelch and --gain-db manually.[/dim]"
                )
                raise typer.Exit(3) from exc
            settings = calibration.settings
            if calibration.mode == "manual":
                console.print(
                    f"[dim]Using manual RF overrides · gain {_gain_label(settings.gain_db)} · "
                    f"squelch {settings.rtl_squelch}[/dim]"
                )
            else:
                console.print(
                    f"[green]✓ RF calibrated[/green] · gain {_gain_label(settings.gain_db)} · "
                    f"squelch {settings.rtl_squelch} · {calibration.attempts} probe(s)"
                )
        else:
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
            )
            console.print(
                f"[yellow]RF auto-calibration disabled[/yellow] · gain {_gain_label(settings.gain_db)} · "
                f"squelch {settings.rtl_squelch}"
            )

        provider = FasterWhisperSpeechProvider(
            model_name=config.speech_model,
            device=config.speech_device,
            compute_type=config.speech_compute_type,
            vad_filter=config.speech_vad_filter,
            local_files_only=config.speech_local_files_only,
        )
        client = TerraSatchApiClient(config.api_url, key)

        console.print(
            f"[green]Listening[/green] {profile.display_name} with Nooelec/RTL-SDR receive only."
        )
        if privacy_code:
            console.print(
                f"[yellow]Privacy code {privacy_code} is context-only in this pilot; "
                "Edge currently receives the full selected carrier.[/yellow]"
            )
        if not once:
            console.print("[dim]Sequential pilot mode: receiver pauses while each call is transcribed/ingested.[/dim]")

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
                )
            except (SpeechProviderUnavailable, SpeechProcessingError, TerraSatchApiError, ValueError) as exc:
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
