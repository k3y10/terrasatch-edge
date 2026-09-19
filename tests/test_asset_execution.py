from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from terrasatch_edge.asset_providers import AssetProviderStatus
from terrasatch_edge.commands import process_edge_commands
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.models import EdgeCommand
from test_commands import FakeCommandClient


class Provider:
    def __init__(self) -> None:
        self.calls = []
        self.ready = True

    def reported_capabilities(self) -> frozenset[str]:
        return frozenset({"camera:capture", "drone:mission"})

    def status(self, asset_id: str) -> AssetProviderStatus:
        return AssetProviderStatus(
            name="test-provider",
            ready=self.ready,
            capabilities=frozenset({"camera:capture", "drone:mission"}),
        )

    def execute(self, mission) -> None:
        self.calls.append(mission)


def _mission_command() -> EdgeCommand:
    return EdgeCommand(
        id=str(uuid4()),
        organization_id=str(uuid4()),
        site_id=str(uuid4()),
        edge_device_id=str(uuid4()),
        command_type="asset_mission",
        payload={
            "mission_id": str(uuid4()),
            "asset_id": str(uuid4()),
            "provider": "test-provider",
            "mission_type": "inspection",
            "objective": "Get eyes on Cardiff",
            "required_capabilities": ["camera:capture"],
            "target": {"location": "Cardiff Bowl"},
            "parameters": {},
        },
        priority=50,
        status="dispatched",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )


def _runtime(command: EdgeCommand):
    config = EdgeConfig(
        device_id=command.edge_device_id,
        organization_id=command.organization_id,
        site_id=command.site_id,
    )
    remote = {
        "assets": {
            "execution_enabled": True,
            "bindings": {
                command.payload["asset_id"]: {
                    "enabled": True,
                    "provider": "test-provider",
                    "allowed_mission_types": ["inspection"],
                }
            },
        }
    }
    provider = Provider()
    return config, remote, provider


def test_asset_mission_executes_only_through_bound_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    command = _mission_command()
    config, remote, provider = _runtime(command)
    client = FakeCommandClient(command)

    cycle = process_edge_commands(
        client,
        config=config,
        remote_config=remote,
        asset_providers={"test-provider": provider},
    )

    assert cycle.ok is True
    assert len(provider.calls) == 1
    assert provider.calls[0].mission_id == command.payload["mission_id"]
    assert client.results[0][1] == "completed"
    assert "1 mission(s) completed" in cycle.summary()


def test_asset_mission_fails_closed_when_policy_is_not_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    command = _mission_command()
    config, remote, provider = _runtime(command)
    remote["assets"]["execution_enabled"] = False
    client = FakeCommandClient(command)

    cycle = process_edge_commands(
        client,
        config=config,
        remote_config=remote,
        asset_providers={"test-provider": provider},
    )

    assert cycle.ok is True
    assert provider.calls == []
    assert client.results[0][1] == "failed"
    assert "policy is disabled" in (client.results[0][2] or "")


def test_terminal_result_retry_never_repeats_physical_effect(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    command = _mission_command()
    config, remote, provider = _runtime(command)
    client = FakeCommandClient(command, fail_first_result=True)

    first = process_edge_commands(
        client,
        config=config,
        remote_config=remote,
        asset_providers={"test-provider": provider},
    )
    second = process_edge_commands(
        client,
        config=config,
        remote_config=remote,
        asset_providers={"test-provider": provider},
    )

    assert first.ok is False
    assert second.ok is True
    assert len(provider.calls) == 1
    assert [item[1] for item in client.results] == ["completed", "completed"]


def test_missing_required_capability_never_calls_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    command = _mission_command()
    command.payload["required_capabilities"] = ["relay:deploy"]
    config, remote, provider = _runtime(command)
    client = FakeCommandClient(command)

    cycle = process_edge_commands(
        client,
        config=config,
        remote_config=remote,
        asset_providers={"test-provider": provider},
    )

    assert cycle.ok is True
    assert provider.calls == []
    assert client.results[0][1] == "failed"
    assert "lacks required" in (client.results[0][2] or "")