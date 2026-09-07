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

    def fake_process(client, *, config=None):
        assert isinstance(client, FakeClient)
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
