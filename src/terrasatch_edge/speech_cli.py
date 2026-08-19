"""Speech-ingestion CLI registration for the native Edge runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import load_api_key, load_config
from .ingest import ingest_audio_file
from .speech import FasterWhisperSpeechProvider, SpeechProcessingError, SpeechProviderUnavailable

console = Console()


def register_speech_commands(app: typer.Typer) -> None:
    """Attach speech commands to the existing native Edge Typer application."""

    @app.command("ingest-audio")
    def ingest_audio(
        audio_path: Annotated[
            Path,
            typer.Argument(help="Bounded WAV/MP3/audio file to transcribe and ingest."),
        ],
        callsign: Annotated[str | None, typer.Option("--callsign")] = None,
        site_id: Annotated[str | None, typer.Option("--site-id")] = None,
        source_message_id: Annotated[str | None, typer.Option("--source-message-id")] = None,
        hotwords: Annotated[
            str | None,
            typer.Option("--hotwords", help="Optional local names/callsigns to bias transcription."),
        ] = None,
    ) -> None:
        """Transcribe local radio audio and send it through the canonical TerraSatch ingest path."""

        config = load_config()
        key = load_api_key()
        if not key:
            console.print("[red]No Edge credential configured. Run `terrasatch-edge setup`.[/red]")
            raise typer.Exit(2)

        provider = FasterWhisperSpeechProvider(
            model_name=config.speech_model,
            device=config.speech_device,
            compute_type=config.speech_compute_type,
            vad_filter=config.speech_vad_filter,
            local_files_only=config.speech_local_files_only,
        )
        client = TerraSatchApiClient(config.api_url, key)
        try:
            result = ingest_audio_file(
                client=client,
                config=config,
                provider=provider,
                audio_path=audio_path,
                callsign=callsign,
                site_id=site_id,
                source_message_id=source_message_id,
                hotwords=hotwords,
                initial_prompt="TerraSatch field radio traffic.",
            )
        except (SpeechProviderUnavailable, SpeechProcessingError, TerraSatchApiError, ValueError) as exc:
            console.print(f"[red]Audio ingestion failed:[/red] {exc}")
            raise typer.Exit(3) from exc

        console.print("[green]✓ Audio transcribed and transmission accepted[/green]")
        console.print(f"Transcript: [bold]{result.transcript.normalized_text}[/bold]")
        console.print(
            f"STT: {result.transcript.provider} / {result.transcript.model} · "
            f"language={result.transcript.language or 'unknown'} · "
            "confidence="
            f"{result.transcript.language_confidence if result.transcript.language_confidence is not None else 'unknown'}"
        )
        console.print_json(json.dumps(result.api_response, default=str))
