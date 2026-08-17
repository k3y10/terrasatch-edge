from __future__ import annotations

import terrasatch_edge.agent as agent_module
from terrasatch_edge.agent import EdgeAgent
from terrasatch_edge.config import EdgeConfig


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
