from __future__ import annotations

import json

from terrasatch_edge.config import EdgeConfig, clear_api_key, get_paths, load_api_key, load_config, save_api_key, save_config


def test_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    config = EdgeConfig(api_url="https://example.invalid", site_id="site-123", node_name="field-1")
    path = save_config(config)
    assert path.exists()
    assert load_config().site_id == "site-123"


def test_default_api_is_production_https(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("TERRASATCH_EDGE_API_URL", raising=False)

    assert load_config().api_url == "https://api.terrasatch.com"


def test_api_url_environment_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("TERRASATCH_EDGE_API_URL", "https://api-staging.example")
    save_config(EdgeConfig(api_url="https://api.terrasatch.com"))

    assert load_config().api_url == "https://api-staging.example"


def test_api_key_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("TERRASATCH_EDGE_API_KEY", raising=False)
    path = save_api_key("secret-test-key")
    assert json.loads(path.read_text())["api_key"] == "secret-test-key"
    assert load_api_key() == "secret-test-key"
    clear_api_key()
    assert load_api_key() is None


def test_paths_follow_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    paths = get_paths()
    assert paths.config_file.parent == tmp_path / "cfg"
    assert paths.snapshot_file.parent == tmp_path / "state"
