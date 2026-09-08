from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from terrasatch_edge.api import TerraSatchApiClient, TerraSatchApiError
from terrasatch_edge.command_journal import CommandJournal
from terrasatch_edge.commands import process_edge_commands
from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_providers import RadioCapability, RadioProviderStatus
from test_commands import FakeCommandClient, _command


class Provider:
    def __init__(self):
        self.calls = []
        self.error = False
        self.ready = True

    def status(self):
        return RadioProviderStatus(
            "test-adapter",
            "independent-tx",
            self.ready,
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
        if self.error:
            raise TimeoutError("uncertain RF outcome")


class Client(FakeCommandClient):
    compatible = True

    def supports_transmitted_results(self):
        return self.compatible

    def remote_config(self):
        return self.policy


@pytest.fixture
def rf(tmp_path, monkeypatch):
    monkeypatch.setenv("TERRASATCH_EDGE_STATE_DIR", str(tmp_path))
    command = _command(simulate_only=False)
    command.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    command.payload.update(
        reply_route="rf",
        action_id=str(uuid4()),
        outbound_transmission_id=str(uuid4()),
        channel_id=str(uuid4()),
    )
    config = EdgeConfig(
        device_id=command.edge_device_id,
        site_id=command.site_id,
        organization_id=command.organization_id,
        radio_tx_enabled=True,
        radio_tx_cooldown_seconds=0,
    )
    remote = {
        "radio": {
            "transmit_enabled": True,
            "ai_channel": {
                "rf_reply_enabled": True,
                "reply_route": "rf",
                "logical_channel_id": command.payload["channel_id"],
                "provider_channel": "ops-5",
                "frequency_hz": 462662500,
                "max_reply_seconds": 5,
                "response_cooldown_seconds": 0,
            },
        }
    }
    client = Client(command)
    client.policy = remote
    return client, config, remote, Provider()


def run(rf):
    client, config, remote, provider = rf
    return process_edge_commands(client, config=config, remote_config=remote, provider=provider)


def test_transmitted_result_is_retried_without_repeating_rf(rf):
    client, config, remote, provider = rf
    client.fail_first_result = True
    assert not run(rf).ok
    second = run(rf)
    assert second.ok
    assert "1 transmitted" in second.summary()
    assert len(provider.calls) == 1
    assert [row[1] for row in client.results] == ["transmitted", "transmitted"]
    assert provider.calls[0].logical_channel_id == client.command.payload["channel_id"]


def test_recorded_outcome_can_report_after_expiry_and_policy_revocation(rf):
    client, config, remote, provider = rf
    client.fail_first_result = True
    run(rf)
    client.command.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    remote.clear()
    assert run(rf).ok
    assert len(provider.calls) == 1
    assert client.results[-1][1] == "transmitted"


def test_uncertain_transmission_is_never_replayed(rf):
    client, _, _, provider = rf
    client.fail_first_result = True
    provider.error = True
    run(rf)
    run(rf)
    assert len(provider.calls) == 1
    assert [row[1] for row in client.results] == ["failed", "failed"]
    assert "uncertain" in client.results[0][2]


@pytest.mark.parametrize(
    "mutation",
    [
        "disabled",
        "missing_provider",
        "old_api",
        "not_ready",
        "expired",
        "missing_deadline",
        "short_deadline",
        "wrong_route",
        "missing_action",
        "empty_text",
        "wrong_channel",
        "disabled_policy",
        "bad_frequency",
        "bad_duration",
        "bad_cooldown",
    ],
)
def test_unapproved_or_unexecutable_requests_never_call_provider(rf, mutation):
    client, config, remote, provider = rf
    ai = remote["radio"]["ai_channel"]
    if mutation == "disabled":
        config.radio_tx_enabled = False
    elif mutation == "missing_provider":
        rf = (client, config, remote, None)
    elif mutation == "old_api":
        client.compatible = False
    elif mutation == "not_ready":
        provider.ready = False
    elif mutation == "expired":
        client.command.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif mutation == "missing_deadline":
        client.command.expires_at = None
    elif mutation == "short_deadline":
        client.command.expires_at = datetime.now(UTC) + timedelta(seconds=1)
    elif mutation == "wrong_route":
        client.command.payload["reply_route"] = "dashboard"
    elif mutation == "missing_action":
        client.command.payload.pop("action_id")
    elif mutation == "empty_text":
        client.command.payload["text"] = ""
    elif mutation == "wrong_channel":
        ai["logical_channel_id"] = str(uuid4())
    elif mutation == "disabled_policy":
        remote["radio"]["transmit_enabled"] = False
    elif mutation == "bad_frequency":
        ai["frequency_hz"] = True
    elif mutation == "bad_duration":
        ai["max_reply_seconds"] = float("nan")
    elif mutation == "bad_cooldown":
        ai["response_cooldown_seconds"] = -1
    run(rf)
    assert not provider.calls
    assert client.results[0][1] == "failed"


def test_inflight_claim_blocks_replay_and_overlapping_commands(rf, tmp_path):
    client, config, _, provider = rf
    scope = "|".join([config.api_url, config.organization_id, config.site_id, config.device_id])
    journal = CommandJournal(tmp_path / "radio-command-journal.sqlite3")
    assert journal.claim(scope, client.command, 0)
    assert not run(rf).ok
    client.command = client.command.model_copy(update={"id": str(uuid4())})
    assert not run(rf).ok
    assert not provider.calls and not client.results


def test_changed_replayed_payload_is_rejected(rf):
    client, _, _, provider = rf
    client.fail_first_result = True
    run(rf)
    client.command.payload["text"] = "different text"
    assert not run(rf).ok
    assert len(provider.calls) == 1


def test_cooldown_defers_next_command(rf):
    client, config, _, provider = rf
    config.radio_tx_cooldown_seconds = 60
    assert run(rf).ok
    client.command = client.command.model_copy(update={"id": str(uuid4()), "status": "dispatched"})
    cycle = run(rf)
    assert not cycle.ok
    assert "cooldown" in cycle.errors[0]
    assert len(provider.calls) == 1


def test_provider_readiness_failure_is_nonfatal(rf, monkeypatch):
    client, _, _, provider = rf

    def fail():
        raise RuntimeError("bridge offline")

    monkeypatch.setattr(provider, "status", fail)
    assert run(rf).ok
    assert client.results[0][1] == "failed"
    assert not provider.calls


@pytest.mark.parametrize("status", [404, 405])
def test_old_api_negotiation_returns_false(monkeypatch, status):
    def request(*args, **kwargs):
        raise TerraSatchApiError("old endpoint", status_code=status)

    client = TerraSatchApiClient("http://localhost")
    monkeypatch.setattr(client, "_request", request)
    assert client.supports_transmitted_results() is False


def test_deadline_is_rechecked_after_waiting_for_execution_lock(rf, monkeypatch):
    import terrasatch_edge.radio_execution as execution

    original_claim = CommandJournal.claim

    class LaterClock:
        @staticmethod
        def now(tz):
            return datetime.now(tz) + timedelta(minutes=10)

    def delayed_claim(*args, **kwargs):
        result = original_claim(*args, **kwargs)
        monkeypatch.setattr(execution, 'datetime', LaterClock)
        return result

    monkeypatch.setattr(CommandJournal, 'claim', delayed_claim)
    client, _, _, provider = rf
    assert run(rf).ok
    assert not provider.calls
    assert client.results[0][1] == 'failed'
    assert 'deadline elapsed' in client.results[0][2]


def test_operator_reconciliation_retains_failed_outcome_and_does_not_replay(rf, tmp_path):
    client, config, _, provider = rf
    scope = '|'.join([config.api_url, config.organization_id, config.site_id, config.device_id])
    journal = CommandJournal(tmp_path / 'radio-command-journal.sqlite3')
    journal.claim(scope, client.command, 0)
    with pytest.raises(ValueError):
        journal.reconcile_failed('wrong-identity', client.command.id)
    journal.reconcile_failed(scope, client.command.id)
    assert run(rf).ok
    assert not provider.calls
    assert client.results[0][1] == 'failed'
    with pytest.raises(ValueError):
        journal.reconcile_failed(scope, client.command.id)


def test_reconciliation_cli_requires_explicit_stop_confirmation():
    from typer.testing import CliRunner
    from terrasatch_edge.cli import app
    result = CliRunner().invoke(app, ['reconcile-radio-command', 'some-command'])
    assert result.exit_code == 2
    assert 'confirm-stopped' in result.output
