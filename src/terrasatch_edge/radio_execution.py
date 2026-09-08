"""Execute only acknowledged API replies through a ready, explicitly configured provider."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from .command_journal import CommandJournal
from .config import EdgeConfig, get_paths
from .models import EdgeCommand
from .radio_providers import RadioCapability, RadioReply, RadioTxProvider


def execute_radio_reply(
    command: EdgeCommand,
    *,
    client,
    config: EdgeConfig,
    remote_config: dict,
    provider: RadioTxProvider | None,
) -> tuple[str, str]:
    scope = "|".join(
        [config.api_url, command.organization_id, command.site_id, command.edge_device_id]
    )
    journal = CommandJournal(get_paths().state_dir / "radio-command-journal.sqlite3")
    previous = journal.previous(scope, command)
    if previous is not None:
        return previous  # report the original outcome even after expiration or policy revocation
    if not config.radio_tx_enabled or provider is None:
        return "failed", "No explicitly enabled local TX provider; no operation performed"
    deadline = command.expires_at
    if deadline is None or deadline.utcoffset() is None or deadline <= datetime.now(UTC):
        return "failed", "RF reply requires a future timezone-aware deadline"
    payload = command.payload
    if payload.get("simulate_only") is not False or payload.get("reply_route") != "rf":
        return "failed", "RF command must explicitly select RF and disable simulation"
    for key in ("action_id", "outbound_transmission_id", "channel_id"):
        try:
            UUID(payload[key])
        except (ValueError, TypeError, KeyError, AttributeError):
            return "failed", f"Approved RF command requires a valid {key}"
    if not isinstance(payload.get("text"), str) or not 1 <= len(payload["text"].strip()) <= 2000:
        return "failed", "RF reply text must contain 1-2000 characters"
    # Re-read policy after ACK, not just once at the beginning of a command batch.
    remote_config = client.remote_config()
    radio = remote_config.get("radio")
    ai = radio.get("ai_channel") if isinstance(radio, dict) else None
    if (
        not isinstance(ai, dict)
        or radio.get("transmit_enabled") is not True
        or ai.get("rf_reply_enabled") is not True
        or ai.get("reply_route") != "rf"
        or ai.get("logical_channel_id") != payload["channel_id"]
    ):
        return "failed", "Current RF policy or logical channel binding does not authorize reply"
    frequency = ai.get("frequency_hz")
    provider_channel = ai.get("provider_channel")
    duration = ai.get("max_reply_seconds", 15)
    cooldown = ai.get("response_cooldown_seconds", 10)
    if (
        type(frequency) is not int
        or not 100_000 <= frequency <= 6_000_000_000
        or not isinstance(provider_channel, str)
        or not provider_channel.strip()
        or type(duration) not in (int, float)
        or not 0 < duration <= 60
        or type(cooldown) not in (int, float)
        or not 0 <= cooldown <= 3600
    ):
        return "failed", "Invalid RF frequency, provider channel, duration or cooldown policy"
    if not client.supports_transmitted_results():
        return "failed", "API does not support transmitted results; no RF operation performed"
    try:
        status = provider.status()
    except Exception as exc:
        return (
            "failed",
            f"TX provider readiness check failed ({type(exc).__name__}); no operation performed",
        )
    if (
        not {
            RadioCapability.TRANSMIT.value,
            RadioCapability.PTT.value,
            RadioCapability.OUTPUT.value,
        }
        <= status.reported_capabilities()
    ):
        return "failed", "TX provider is unavailable or simulation-only"
    duration = min(duration, config.radio_tx_max_seconds)
    if (deadline - datetime.now(UTC)).total_seconds() < duration:
        return "failed", "Insufficient time remaining for bounded RF reply"
    if not journal.claim(scope, command, max(cooldown, config.radio_tx_cooldown_seconds)):
        previous = journal.previous(scope, command)
        if previous is None:
            raise RuntimeError("RF journal claim unavailable")
        return previous
    if (deadline - datetime.now(UTC)).total_seconds() < duration:
        outcome = ('failed', 'RF deadline elapsed while claiming execution; no operation performed')
        journal.finish(scope, command, outcome)
        return outcome
    try:
        provider.transmit(
            RadioReply(
                command.id,
                payload["text"],
                payload["channel_id"],
                provider_channel,
                frequency,
                duration,
            )
        )
        outcome = ("transmitted", "Provider confirmed transmission, PTT release and RX restoration")
    except Exception as exc:
        # A failed process/timeout may have emitted RF: preserve uncertainty and never retry RF.
        outcome = (
            "failed",
            f"RF attempt failed or outcome uncertain ({type(exc).__name__}); will not replay",
        )
    journal.finish(scope, command, outcome)
    return outcome
