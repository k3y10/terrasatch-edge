"""Regression cases for branch integration, provenance, and fail-closed control."""
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from terrasatch_edge.api import TerraSatchApiClient, reported_capabilities
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_context import radio_source
from terrasatch_edge.radio_providers import RadioCapability, RadioProviderStatus, SimulationRadioProvider
from terrasatch_edge.radio_service import RadioMonitorService, resolve_radio_config
from test_api import _snapshot
from test_commands import FakeCommandClient, _command
from test_radio_service import FakeClient, FakeProvider, _capture
from terrasatch_edge.commands import process_edge_commands
from terrasatch_edge.models import DeviceKind, HardwareDevice


@pytest.mark.parametrize('channel', range(1, 23))
def test_long_source_preserves_each_physical_channel(channel):
    source = radio_source('x' * 100, channel)
    assert len(source) <= 64
    assert source.endswith(f'-radio-bca-ch{channel:02d}')


def test_audio_request_uses_object_rf_metadata(monkeypatch):
    bodies = []
    def request(method, url, **kwargs):
        bodies.append(kwargs['json'])
        return httpx.Response(200, json={}, request=httpx.Request(method, url))
    monkeypatch.setattr(httpx, 'request', request)
    TerraSatchApiClient('http://localhost').ingest_text(site_id='site', text='original')
    assert bodies[0]['rf_metadata'] == {}


@pytest.mark.parametrize('radio', [
    {'enabled': False, 'processing': {'min_transmission_seconds': -1}},
    {'receive_enabled': False, 'enabled': True},
    {'profile': 'unimplemented-provider'},
    {'channel_bindings': {'23': 'channel-id'}},
    'invalid',
])
def test_invalid_or_disabled_remote_config_cannot_enable_receive(radio):
    assert resolve_radio_config(EdgeConfig(), {'radio': radio}).config.enabled is False


def test_capture_payload_preserves_raw_text_and_specific_channel_binding(tmp_path):
    edge = EdgeConfig(site_id='site', radio_channel=5, source='x' * 100)
    config = resolve_radio_config(edge, {'radio': {
        'logical_channel_id': 'legacy',
        'channel_bindings': {'5': 'patrol', '9': 'rescue'},
    }}).config
    service = RadioMonitorService(edge_config=edge, monitor_config=config,
                                  provider=FakeProvider(), client=FakeClient(), state_dir=tmp_path)
    capture = _capture(tmp_path / 'audio.wav', 'stable-id')
    transcript = FakeProvider().transcribe(capture.path)
    transcript.raw_text = '  Control TWO, Satchy.  '
    transcript.normalized_text = 'rewritten'
    payload = service._payload_for(capture, transcript)
    assert payload['text'] == transcript.raw_text
    assert payload['channel_id'] == 'patrol'
    assert payload['source'].endswith('-ch05')
    assert config.channel_id_for(9) == 'rescue'
    assert config.channel_id_for(7) is None
    assert payload['rf_metadata']['tone_detected'] is False


def test_legacy_binding_does_not_leak_to_another_carrier():
    config = resolve_radio_config(EdgeConfig(radio_channel=5),
                                 {'radio': {'logical_channel_id': 'patrol'}}).config
    assert config.channel_id_for(5) == 'patrol'
    assert config.channel_id_for(9) is None


@pytest.mark.parametrize('capability', list(RadioCapability))
def test_hardware_labels_do_not_grant_radio_operations(monkeypatch, capability):
    monkeypatch.setattr('terrasatch_edge.api.find_executable', lambda _: None)
    device = HardwareDevice(kind=DeviceKind.USB, name='unknown', identifier='usb',
                            capabilities=[capability.value])
    assert capability.value not in reported_capabilities(_snapshot(device))


def test_simulation_and_unready_provider_never_advertise_tx():
    assert SimulationRadioProvider().status().reported_capabilities() == set()
    status = RadioProviderStatus('adapter', 'tx-device', False,
                                 frozenset({RadioCapability.TRANSMIT}))
    assert status.reported_capabilities() == set()


def test_wrong_tenant_command_is_not_acknowledged():
    client = FakeCommandClient(_command())
    cycle = process_edge_commands(client, config=EdgeConfig(
        device_id=client.command.edge_device_id, site_id=client.command.site_id,
        organization_id='different-org'))
    assert not cycle.ok
    assert not client.acks and not client.results


@pytest.mark.parametrize('status', ['completed', 'failed', 'expired', 'unexpected'])
def test_terminal_commands_are_not_replayed(status):
    client = FakeCommandClient(_command(status=status))
    assert not process_edge_commands(client).ok
    assert not client.acks and not client.results


def test_expired_acknowledged_command_is_not_simulated():
    command = _command(status='acknowledged').model_copy(update={
        'expires_at': datetime.now(UTC) - timedelta(seconds=1)})
    client = FakeCommandClient(command)
    process_edge_commands(client)
    assert client.results[0][1] == 'failed'
    assert 'Expired' in client.results[0][2]


def test_ack_cannot_replace_command_payload():
    class ChangedAck(FakeCommandClient):
        def acknowledge_edge_command(self, command_id):
            ack = super().acknowledge_edge_command(command_id)
            return ack.model_copy(update={'payload': {'simulate_only': True, 'text': 'changed'}})
    client = ChangedAck(_command())
    assert not process_edge_commands(client).ok
    assert not client.results


def test_conflicting_simulation_route_is_failed():
    command = _command()
    command.payload['reply_route'] = 'rf'
    client = FakeCommandClient(command)
    process_edge_commands(client)
    assert client.results[0][1] == 'failed'


@pytest.mark.parametrize(('frequency', 'expected'), [(462662500, 'patrol'), (462562500, None), (None, None)])
def test_existing_api_ai_channel_binding_requires_matching_frequency(frequency, expected):
    config = resolve_radio_config(EdgeConfig(radio_channel=5), {'radio': {'ai_channel': {
        'logical_channel_id': 'patrol', 'frequency_hz': frequency,
    }}}).config
    assert config.channel_id_for(5) == expected


def test_malformed_route_fails_without_crashing_command_cycle():
    command = _command()
    command.payload['reply_route'] = ['rf']
    client = FakeCommandClient(command)
    assert process_edge_commands(client).ok
    assert client.results[0][1] == 'failed'
