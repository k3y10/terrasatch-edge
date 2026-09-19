from __future__ import annotations

import terrasatch_edge.agent as agent_module
from terrasatch_edge.agent import EdgeAgent
from terrasatch_edge.commands import CommandCycle, CommandOutcome
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.models import SystemSnapshot


def test_agent_picks_up_pairing_without_service_restart(monkeypatch):
    monkeypatch.setattr(agent_module, "load_config", lambda: EdgeConfig(api_url="https://api-old.example"))
    monkeypatch.setattr(agent_module, "load_api_key", lambda: None)
    agent = EdgeAgent()

    monkeypatch.setattr(
        agent_module,
        "load_config",
        lambda: EdgeConfig(
            api_url="https://api.terrasatch.com",
            device_id="device-1",
            site_id="site-1",
        ),
    )
    monkeypatch.setattr(agent_module, "load_api_key", lambda: "paired-key")

    agent._reload_registration()

    assert agent.config.api_url == "https://api.terrasatch.com"
    assert agent.config.device_id == "device-1"
    assert agent.config.site_id == "site-1"
    assert agent.api_key == "paired-key"
    assert agent.client.base_url == "https://api.terrasatch.com"
    assert agent.client.api_key == "paired-key"


def test_agent_tick_keeps_receive_scan_and_processes_commands_after_sync(monkeypatch) -> None:
    config = EdgeConfig(
        api_url="https://api.terrasatch.com",
        device_id="device-1",
        site_id="site-1",
    )
    snapshot = SystemSnapshot(
        hostname="edge-test",
        platform="test",
        platform_release="1",
        architecture="x86_64",
        python_version="3.12",
    )
    events: list[str] = []

    class FakeClient:
        def heartbeat(self, received_snapshot, *, telemetry=None):
            assert received_snapshot is snapshot
            events.append("heartbeat")
            return {"device": {"name": "Edge 1"}}

        def remote_config(self):
            events.append("config")
            return {"radio": {"receive_enabled": True, "transmit_enabled": False}}

    monkeypatch.setattr(agent_module, "load_config", lambda: config)
    monkeypatch.setattr(agent_module, "load_api_key", lambda: "paired-key")
    monkeypatch.setattr(agent_module, "scan_hardware", lambda **_kwargs: snapshot)
    monkeypatch.setattr(agent_module, "save_snapshot", lambda _snapshot: events.append("snapshot"))
    monkeypatch.setattr(agent_module, "save_remote_config", lambda _config: events.append("save_config"))

    def fake_process(
        client,
        *,
        config=None,
        remote_config=None,
        provider=None,
        asset_providers=None,
    ):
        assert isinstance(client, FakeClient)
        assert asset_providers == {}
        events.append("commands")
        return CommandCycle(
            polled=1,
            outcomes=[
                CommandOutcome(
                    command_id="command-1",
                    command_type="radio_reply",
                    result="simulated",
                    detail="No RF/PTT operation was attempted",
                )
            ],
        )

    monkeypatch.setattr(agent_module, "process_edge_commands", fake_process)
    agent = EdgeAgent()
    agent.client = FakeClient()  # type: ignore[assignment]

    ok, message = agent.tick()

    assert ok is True
    assert events == ["snapshot", "heartbeat", "config", "save_config", "commands"]
    assert "1 command(s) polled; 1 simulated" in message


def test_agent_advertises_and_routes_only_negotiated_asset_providers(monkeypatch) -> None:
    config = EdgeConfig(
        api_url="https://api.terrasatch.com",
        device_id="device-asset",
        organization_id="org-asset",
        site_id="site-asset",
    )
    snapshot = SystemSnapshot(
        hostname="edge-asset",
        platform="test",
        platform_release="1",
        architecture="x86_64",
        python_version="3.12",
    )
    events: list[object] = []

    class AssetProvider:
        def reported_capabilities(self):
            return frozenset({"camera:capture", "drone:mission"})

        def status(self, _asset_id):
            raise AssertionError("status is not needed during heartbeat capability reporting")

        def execute(self, _mission):
            raise AssertionError("no mission should execute in this test")

    asset_provider = AssetProvider()

    class FakeClient:
        def supports_asset_results(self):
            events.append("negotiate")
            return True

        def heartbeat(self, received_snapshot, *, telemetry=None, provider_capabilities=None):
            assert received_snapshot is snapshot
            assert provider_capabilities == {"camera:capture", "drone:mission"}
            events.append(("heartbeat", provider_capabilities))
            return {"device": {"name": "Edge Asset"}}

        def remote_config(self):
            events.append("config")
            return {"assets": {"execution_enabled": True, "bindings": {}}}

    monkeypatch.setattr(agent_module, "load_config", lambda: config)
    monkeypatch.setattr(agent_module, "load_api_key", lambda: "paired-key")
    monkeypatch.setattr(agent_module, "scan_hardware", lambda **_kwargs: snapshot)
    monkeypatch.setattr(agent_module, "save_snapshot", lambda _snapshot: events.append("snapshot"))
    monkeypatch.setattr(agent_module, "save_remote_config", lambda _config: events.append("save_config"))

    def fake_process(
        client,
        *,
        config=None,
        remote_config=None,
        provider=None,
        asset_providers=None,
    ):
        assert isinstance(client, FakeClient)
        assert asset_providers == {"test-provider": asset_provider}
        events.append("commands")
        return CommandCycle()

    monkeypatch.setattr(agent_module, "process_edge_commands", fake_process)
    agent = EdgeAgent(asset_providers={"test-provider": asset_provider})
    agent.client = FakeClient()  # type: ignore[assignment]

    ok, _message = agent.tick()

    assert ok is True
    assert events == [
        "snapshot",
        "negotiate",
        ("heartbeat", {"camera:capture", "drone:mission"}),
        "config",
        "save_config",
        "commands",
    ]


def test_agent_does_not_advertise_assets_to_incompatible_api(monkeypatch) -> None:
    config = EdgeConfig(
        api_url="https://api.terrasatch.com",
        device_id="device-asset",
        organization_id="org-asset",
        site_id="site-asset",
    )
    snapshot = SystemSnapshot(
        hostname="edge-asset",
        platform="test",
        platform_release="1",
        architecture="x86_64",
        python_version="3.12",
    )

    class AssetProvider:
        def reported_capabilities(self):
            return frozenset({"camera:capture"})

        def status(self, _asset_id):
            raise AssertionError

        def execute(self, _mission):
            raise AssertionError

    class FakeClient:
        def supports_asset_results(self):
            return False

        def heartbeat(self, received_snapshot, *, telemetry=None, provider_capabilities=None):
            assert received_snapshot is snapshot
            assert provider_capabilities is None
            return {"device": {"name": "Edge Asset"}}

        def remote_config(self):
            return {}

    monkeypatch.setattr(agent_module, "load_config", lambda: config)
    monkeypatch.setattr(agent_module, "load_api_key", lambda: "paired-key")
    monkeypatch.setattr(agent_module, "scan_hardware", lambda **_kwargs: snapshot)
    monkeypatch.setattr(agent_module, "save_snapshot", lambda _snapshot: None)
    monkeypatch.setattr(agent_module, "save_remote_config", lambda _config: None)

    def fake_process(
        client,
        *,
        config=None,
        remote_config=None,
        provider=None,
        asset_providers=None,
    ):
        assert asset_providers == {}
        return CommandCycle()

    monkeypatch.setattr(agent_module, "process_edge_commands", fake_process)
    agent = EdgeAgent(asset_providers={"test-provider": AssetProvider()})
    agent.client = FakeClient()  # type: ignore[assignment]

    ok, _message = agent.tick()
    assert ok is True
