from __future__ import annotations

from terrasatch_edge.config import EdgeConfig, load_config, save_config, update_registration_config


def test_radio_defaults_are_safe_for_bounded_receive() -> None:
    config = EdgeConfig()
    assert config.radio_profile == "bca-frs-na"
    assert config.radio_channel is None
    assert config.radio_squelch > 0
    assert config.radio_output_sample_rate == 16_000
    assert config.radio_auto_calibrate is True
    assert config.radio_release_rms_threshold < config.radio_min_peak_rms


def test_radio_env_overrides_load_without_destroying_saved_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    save_config(EdgeConfig(site_id="site-1", speech_model="small.en", radio_channel=3))
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_CHANNEL", "5")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_SQUELCH", "24")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_MAX_SECONDS", "12")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_CALIBRATION_SECONDS", "0.75")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_RELEASE_RMS_THRESHOLD", "90")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_AUTO_CALIBRATE", "false")
    loaded = load_config()
    assert loaded.site_id == "site-1"
    assert loaded.speech_model == "small.en"
    assert loaded.radio_channel == 5
    assert loaded.radio_squelch == 24
    assert loaded.radio_max_transmission_seconds == 12
    assert loaded.radio_calibration_seconds == 0.75
    assert loaded.radio_release_rms_threshold == 90
    assert loaded.radio_auto_calibrate is False


def test_malformed_optional_radio_env_is_ignored(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TERRASATCH_EDGE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path / "state"))
    save_config(EdgeConfig(site_id="site-1", radio_channel=7, radio_gain_db=28.0))
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_CHANNEL", "not-a-number")
    monkeypatch.setenv("TERRASATCH_EDGE_RADIO_GAIN_DB", "bad")
    loaded = load_config()
    assert loaded.site_id == "site-1"
    assert loaded.radio_channel == 7
    assert loaded.radio_gain_db == 28.0


def test_registration_update_preserves_speech_and_radio_tuning() -> None:
    current = EdgeConfig(
        speech_model="small.en",
        speech_compute_type="int8_float16",
        radio_channel=5,
        radio_squelch=26,
        radio_gain_db=28.0,
    )
    updated = update_registration_config(
        current,
        api_url="https://api.terrasatch.com",
        device_id="device-2",
        organization_id="org-2",
        site_id="site-2",
        site_name="Wasatch",
        node_name="field-edge",
    )
    assert updated.device_id == "device-2"
    assert updated.site_id == "site-2"
    assert updated.speech_model == "small.en"
    assert updated.speech_compute_type == "int8_float16"
    assert updated.radio_channel == 5
    assert updated.radio_squelch == 26
    assert updated.radio_gain_db == 28.0
