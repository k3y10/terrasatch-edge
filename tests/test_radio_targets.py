from dataclasses import replace

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from terrasatch_edge.cli import app
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_receiver import RadioReceiveSettings, build_rtl_fm_command
from terrasatch_edge.radio_service import resolve_radio_config
from terrasatch_edge.radio_targets import RadioTarget, bca_target, direct_target, parse_frequency


@pytest.mark.parametrize("value", [462650000, "462650000", "462.650M", "462.650MHz", "462650kHz", "0.46265GHz"])
def test_frequency_forms(value):
    assert parse_frequency(value) == 462650000


@pytest.mark.parametrize("value", [True, 0, -1, "NaN", "inf", "462M;echo bad", "1.1Hz", "9G", "", "-462M"])
def test_frequency_rejects_invalid(value):
    with pytest.raises(ValueError):
        parse_frequency(value)


@pytest.mark.parametrize("channel", range(1, 23))
def test_bca_settings_and_target_use_identical_receiver(channel):
    legacy = RadioReceiveSettings(channel=channel)
    explicit = replace(legacy, channel=None, target=bca_target(channel))
    assert build_rtl_fm_command(legacy) == build_rtl_fm_command(explicit)


def test_channel_19_and_direct_frequency_same_rf_command():
    assert bca_target(19).frequency_hz == 462650000
    assert build_rtl_fm_command(RadioReceiveSettings(channel=19)) == build_rtl_fm_command(
        RadioReceiveSettings(target=direct_target("462.650M")))


@pytest.mark.parametrize("changes", [dict(frequency_hz=True), dict(frequency_hz=1.2), dict(modulation="p25"),
                                      dict(enabled="false"), dict(transmit_authorized=True), dict(id="../bad"),
                                      dict(channel=19), dict(organization_id="evil"), dict(ctcss_hz=float("nan"))])
def test_target_validation(changes):
    with pytest.raises(ValidationError):
        RadioTarget.model_validate(dict(id="manual", name="Manual", frequency_hz=462650000) | changes)


@pytest.mark.parametrize("frequency", ["23M", "1767M"])
def test_receiver_rejects_outside_tuner_range(frequency):
    with pytest.raises(ValueError, match="25-1750"):
        build_rtl_fm_command(RadioReceiveSettings(target=direct_target(frequency)))


def test_repeater_output_is_selected_and_input_preserved():
    target = RadioTarget(id="cottonwood", name="Cottonwood", frequency_hz=462650000,
                         source_type="repeater", repeater=dict(output_frequency_hz=462650000,
                         input_frequency_hz=467650000))
    assert target.rf_metadata()["repeater"]["input_frequency_hz"] == 467650000
    with pytest.raises(ValidationError):
        RadioTarget.model_validate(target.model_dump() | dict(frequency_hz=467650000))


def test_remote_targets_identity_and_policy_boundary():
    edge = EdgeConfig(site_id="paired", radio_tx_enabled=False)
    target = direct_target("462.650M")
    resolved = resolve_radio_config(edge, {"radio": {"targets": [target.model_dump()],
        "receivers": [{"name": "primary", "device_index": 0}], "organization_id": "evil",
        "radio_tx_enabled": True}})
    assert resolved.config.selected_target() == target
    assert edge.site_id == "paired" and edge.radio_tx_enabled is False
    assert resolve_radio_config(edge, {"radio": {"enabled": True, "receive_enabled": False}}).config.enabled is False


def test_local_targets_survive_directory_absence_and_remote_failure_is_closed():
    target = direct_target("462.650M").model_dump()
    edge = EdgeConfig(radio={"targets": [target]})
    assert resolve_radio_config(edge).config.selected_target().frequency_hz == 462650000
    for radio in [{"targets": [{"frequency_hz": "bad"}]}, {"targets": [target, target]},
                  {"enabled": "false"}, {"processing": "bad"}]:
        result = resolve_radio_config(edge, {"radio": radio})
        assert not result.config.enabled
        assert result.warnings
    assert resolve_radio_config(edge).config.enabled


@pytest.mark.parametrize("command", [["setup"], ["doctor"], ["radio-channels"], ["listen-radio"],
                                    ["radio", "start"], ["radio", "stop"], ["radio", "status"],
                                    ["radio", "devices"], ["radio", "targets"], ["radio", "probe"],
                                    ["radio", "scan"], ["radio", "discover"]])
def test_cli_legacy_and_new_help(command):
    assert CliRunner().invoke(app, command + ["--help"]).exit_code == 0


def test_direct_start_resolves_target_and_preserves_site(monkeypatch, tmp_path):
    import terrasatch_edge.radio_cli as cli
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "load_config", lambda: EdgeConfig(site_id="paired"))
    monkeypatch.setattr(cli, "load_api_key", lambda: "local-test")
    seen = []
    monkeypatch.setattr(cli.RadioMonitorService, "run_forever", lambda self: seen.append(self))
    result = CliRunner().invoke(app, ["radio", "start", "--frequency", "462.650M", "--no-auto-calibrate"])
    assert result.exit_code == 0, result.output
    assert seen[0].target.frequency_hz == 462650000
    assert seen[0].channel is None
    assert seen[0].edge_config.site_id == "paired"


def test_unconfigured_start_never_opens_receiver(monkeypatch, tmp_path):
    import terrasatch_edge.radio_cli as cli
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "load_config", lambda: EdgeConfig(site_id="paired"))
    monkeypatch.setattr(cli, "load_api_key", lambda: "local-test")
    result = CliRunner().invoke(app, ["radio", "start"])
    assert result.exit_code == 2
    assert "Configure a receive target" in result.output


def test_missing_credentials_preserves_non_retryable_service_exit(monkeypatch, tmp_path):
    import terrasatch_edge.radio_cli as cli
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "load_api_key", lambda: None)
    result = CliRunner().invoke(app, ["radio", "start", "--frequency", "462.650M"])
    assert result.exit_code == 2
    assert "No Edge credential configured" in result.output
    assert "Radio operation failed: 2" not in result.output
