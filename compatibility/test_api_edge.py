"""Run against either the deployed API source or proposed API branch.

Uses actual bearer authentication, routes, ORM models, ingestion and action services.
Only database connection factories and the external event bus are replaced.
"""

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import terrasatch.api.radio as radio_api
import terrasatch.auth.dependencies as auth
import terrasatch.edge.api as edge_api
from terrasatch.actions.models import SatchyAction
from terrasatch.actions.service import approve_and_queue_action
from terrasatch.auth.api_keys import hash_api_key
from terrasatch.config import Settings
from terrasatch.main import create_app
from terrasatch.outbound.models import OutboundTransmission
from terrasatch_edge.api import TerraSatchApiClient, TerraSatchApiError
from terrasatch_edge.commands import process_edge_commands
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_providers import RadioCapability, RadioProviderStatus
from test_satchy_control_plane import _seed_session

EXPECT_TX = os.environ.get("TERRASATCH_JOINT_EXPECT_TX", "0") == "1"


class Provider:
    def __init__(self):
        self.calls = []

    def status(self):
        return RadioProviderStatus(
            "contract-test",
            "tx-device",
            True,
            frozenset(
                {
                    RadioCapability.TRANSMIT,
                    RadioCapability.PTT,
                    RadioCapability.OUTPUT,
                    RadioCapability.HALF_DUPLEX,
                }
            ),
        )

    def transmit(self, reply):
        self.calls.append(reply)


@pytest.fixture
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "edge"))
    engine, session, seeded = asyncio.run(_seed_session())
    token = "local-contract-test-token"
    seeded["keys"][0].secret_hash = hash_api_key(token)
    seeded["devices"][0].last_seen_at = datetime.now(UTC)
    seeded["devices"][0].capabilities = ["radio:receive", "radio:transmit"]
    asyncio.run(session.commit())
    asyncio.run(session.close())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    for module in (auth, edge_api, radio_api):
        monkeypatch.setattr(module, "create_session_factory", lambda _: factory)

    async def publish(*args, **kwargs):
        pass

    monkeypatch.setattr(radio_api, "publish_event", publish)
    app = create_app(Settings(environment="local", intelligence_provider="deterministic"))
    with TestClient(app) as http:
        monkeypatch.setattr(
            httpx, "request", lambda method, url, **kwargs: http.request(method, url, **kwargs)
        )
        client = TerraSatchApiClient("http://testserver", token)
        device = client.edge_me()
        config = EdgeConfig(
            api_url=client.base_url,
            device_id=device.id,
            site_id=device.site_id,
            organization_id=device.organization_id,
            radio_tx_enabled=True,
            radio_tx_cooldown_seconds=0,
        )
        yield client, config, seeded, factory, http
    asyncio.run(engine.dispose())


def ingest(stack):
    client, config, seeded, _, _ = stack
    return client.ingest_text(
        site_id=config.site_id,
        channel_id=str(seeded["channel"].id),
        text="Satchy, Control 2.",
        source_message_id=str(uuid4()),
    )


def approve(stack, transmission, rf=False):
    client, config, seeded, factory, _ = stack

    async def operation():
        async with factory() as session:
            device = await session.get(type(seeded["devices"][0]), UUID(config.device_id))
            remote = {
                "radio": {
                    "transmit_enabled": rf,
                    "ai_channel": {
                        "rf_reply_enabled": rf,
                        "reply_route": "rf" if rf else "dashboard",
                        "logical_channel_id": str(seeded["channel"].id),
                        "provider_channel": "ops-5",
                        "frequency_hz": 462662500,
                        "max_reply_seconds": 1,
                        "response_cooldown_seconds": 0,
                    },
                }
            }
            device.remote_config = remote
            action = await session.scalar(
                select(SatchyAction).where(
                    SatchyAction.source_transmission_id == UUID(transmission["transmission"]["id"])
                )
            )
            if not rf:
                action.expires_at = None  # valid optional-deadline contract on both API versions
            _, _, outbound, command = await approve_and_queue_action(
                session,
                organization_id=device.organization_id,
                action_id=action.id,
                approver_role="admin",
            )
            await session.commit()
            return str(outbound.id), remote

    return asyncio.run(operation())


def outcome(stack, outbound_id):
    async def query():
        async with stack[3]() as session:
            record = await session.get(OutboundTransmission, UUID(outbound_id))
            return record.status

    return asyncio.run(query())


def test_current_ingest_contract_preserves_text_metadata_and_idempotency(stack):
    client, config, seeded, _, _ = stack
    payload = dict(
        site_id=config.site_id,
        channel_id=str(seeded["channel"].id),
        text="Control 2 reports wind.",
        source_message_id=str(uuid4()),
        rf_metadata={"channel": 5, "frequency_hz": 462662500, "tone_detected": False},
    )
    first = client.ingest_text(**payload)
    second = client.ingest_text(**payload)
    assert second["duplicate"] is True
    assert first["transmission"]["id"] == second["transmission"]["id"]
    assert first["transcript"]["raw_text"] == payload["text"]
    assert first["transmission"]["rf_metadata"]["channel"] == 5
    assert client.supports_transmitted_results() is EXPECT_TX


def test_simulation_round_trip_remains_compatible(stack):
    client, config, _, _, _ = stack
    outbound_id, remote = approve(stack, ingest(stack))
    cycle = process_edge_commands(client, config=config, remote_config=remote)
    assert cycle.ok, cycle.errors
    assert cycle.outcomes[0].result == "simulated"
    assert outcome(stack, outbound_id) == "simulated"
    assert client.edge_commands() == []


def test_rf_round_trip_negotiates_api_and_retries_result_without_second_send(stack, monkeypatch):
    client, config, _, _, _ = stack
    outbound_id, remote = approve(stack, ingest(stack), rf=True)
    provider = Provider()
    real_report = client.report_edge_command_result
    report_calls = []

    def lose_first_result(*args, **kwargs):
        report_calls.append(kwargs["status"])
        if len(report_calls) == 1:
            raise TerraSatchApiError("test connection lost before result delivery")
        return real_report(*args, **kwargs)

    monkeypatch.setattr(client, "report_edge_command_result", lose_first_result)
    first = process_edge_commands(client, config=config, remote_config=remote, provider=provider)
    second = process_edge_commands(client, config=config, remote_config=remote, provider=provider)
    assert not first.ok
    assert second.ok, second.errors
    expected = "transmitted" if EXPECT_TX else "failed"
    assert outcome(stack, outbound_id) == expected
    assert report_calls == [expected, expected]
    assert len(provider.calls) == (1 if EXPECT_TX else 0)


def test_foreign_device_cannot_poll_or_ack_assigned_command(stack):
    client, _, seeded, factory, _ = stack
    approve(stack, ingest(stack))
    assigned = client.edge_commands()[0]

    async def set_key():
        async with factory() as session:
            key = await session.get(type(seeded["keys"][1]), seeded["keys"][1].id)
            key.secret_hash = hash_api_key("other-test-device")
            await session.commit()

    asyncio.run(set_key())
    other = TerraSatchApiClient(client.base_url, "other-test-device")
    assert other.edge_commands() == []
    with pytest.raises(TerraSatchApiError):
        other.acknowledge_edge_command(assigned.id)
