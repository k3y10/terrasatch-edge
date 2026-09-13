"""Actual authenticated API config -> Edge -> outbox -> ingest round trip."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from test_api_edge import stack  # noqa: F401
from terrasatch_edge.radio_receiver import RadioAudioCapture
from terrasatch_edge.radio_service import RadioMonitorService, resolve_radio_config
from terrasatch_edge.radio_targets import RadioTarget
from terrasatch_edge.speech import SpeechTranscript


@pytest.mark.parametrize("frequency", [462650000, 462662500])
def test_config_target_outbox_ingest_provenance_and_idempotency(stack, tmp_path, frequency):  # noqa: F811 - shared pytest fixture
    client, edge, seeded, factory, http = stack
    target = RadioTarget(id="cottonwood", name="Cottonwood Repeater", profile="gmrs-repeater",
                         source_type="repeater", frequency_hz=frequency,
                         repeater=dict(output_frequency_hz=frequency, input_frequency_hz=frequency+5000000))
    remote = dict(radio=dict(enabled=True, receivers=[dict(name="primary", device_index=0)],
                            targets=[target.model_dump()]))

    async def assign():
        async with factory() as session:
            device = await session.get(type(seeded["devices"][0]), UUID(edge.device_id))
            device.remote_config = remote
            await session.commit()
    asyncio.run(assign())
    response = http.get("/api/v1/edge/config", headers=client._headers())
    assert response.status_code == 200
    config = resolve_radio_config(edge, response.json()).config
    assert config.selected_target() == target
    service = RadioMonitorService(edge_config=edge, monitor_config=config,
                                  provider=None, client=client, state_dir=tmp_path)
    now = datetime.now(UTC)
    capture = RadioAudioCapture(path=tmp_path / "unused.wav", channel=None, target=target,
        duration_seconds=1, peak_rms=1000, source_message_id=str(uuid4()), started_at=now,
        ended_at=now+timedelta(seconds=1))
    transcript = SpeechTranscript(raw_text="Control reports clear access.", normalized_text="Control reports clear access.",
                                  provider="faster_whisper", model="base.en", language="en")
    payload = service._payload_for(capture, transcript)
    service.outbox.enqueue(capture.source_message_id, payload)
    queued = service.outbox.due()
    first = client.ingest_text(**queued.payload)
    second = client.ingest_text(**queued.payload)
    assert second["duplicate"]
    service.outbox.delivered(capture.source_message_id)
    assert service.outbox.depth() == 0
    rf = first["transmission"]["rf_metadata"]
    assert rf["target_id"] == "cottonwood" and rf["frequency_hz"] == frequency
    assert rf["modulation"] == "nfm" and rf["source_type"] == "repeater"
    assert rf["repeater"]["input_frequency_hz"] == frequency + 5000000
    assert rf["snr_db"] is None and rf["signal_dbfs"] is None
    assert first["transmission"]["site_id"] == edge.site_id
