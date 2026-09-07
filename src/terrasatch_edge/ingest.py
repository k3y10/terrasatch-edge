"""Canonical speech-to-TerraSatch ingestion helpers."""

from __future__ import annotations

import platform
import uuid
from pathlib import Path
from typing import Any
from datetime import datetime

from pydantic import BaseModel

from .api import TerraSatchApiClient
from .config import EdgeConfig
from .speech import SpeechToTextProvider, SpeechTranscript


class AudioIngestResult(BaseModel):
    source_message_id: str
    transcript: SpeechTranscript
    api_response: dict[str, Any]


def ingest_audio_file(
    *,
    client: TerraSatchApiClient,
    config: EdgeConfig,
    provider: SpeechToTextProvider,
    audio_path: str | Path,
    callsign: str | None = None,
    site_id: str | None = None,
    source_message_id: str | None = None,
    source: str | None = None,
    agent_id: str | None = None,
    channel_id: str | None = None,
    hotwords: str | None = None,
    initial_prompt: str | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    rf_metadata: dict[str, Any] | None = None,
) -> AudioIngestResult:
    """Transcribe a bounded audio file and submit it through `/api/v1/transmissions`."""

    target_site = site_id or config.site_id
    if not target_site:
        raise ValueError("A TerraSatch site is required for audio ingestion")

    transcript = provider.transcribe(
        audio_path,
        language=config.speech_language,
        hotwords=hotwords,
        initial_prompt=initial_prompt,
    )
    message_id = source_message_id or f"edge-audio-{platform.node()}-{uuid.uuid4()}"
    response = client.ingest_text(
        site_id=target_site,
        text=transcript.raw_text,
        callsign=callsign,
        source_message_id=message_id,
        source=source or f"{config.source}-stt",
        agent_id=agent_id,
        channel_id=channel_id,
        transcript_provider=transcript.provider,
        transcript_model=transcript.model,
        transcript_language=transcript.language,
        transcript_confidence=transcript.language_confidence,
        started_at=started_at.isoformat() if started_at is not None else None,
        ended_at=ended_at.isoformat() if ended_at is not None else None,
        rf_metadata=rf_metadata,
    )
    return AudioIngestResult(
        source_message_id=message_id,
        transcript=transcript,
        api_response=response,
    )
