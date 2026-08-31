from __future__ import annotations

from datetime import UTC, datetime

from terrasatch_edge.models import EdgeCommand, PairingClaim, PairingStart


def test_pairing_start_parses_api_contract() -> None:
    result = PairingStart.model_validate(
        {
            "pairing_id": "11111111-1111-1111-1111-111111111111",
            "device_code": "super-secret-device-code-abcdefghijklmnopqrstuvwxyz",
            "user_code": "ABCD-2345",
            "verification_url": "https://api.terrasatch.com/admin/edge/pair?code=ABCD-2345",
            "expires_at": datetime.now(UTC).isoformat(),
            "interval_seconds": 5,
        }
    )
    assert result.user_code == "ABCD-2345"
    assert result.interval_seconds == 5


def test_pending_pairing_claim_needs_no_token() -> None:
    claim = PairingClaim.model_validate({"status": "pending", "token": None, "device": None})
    assert claim.status == "pending"
    assert claim.token is None


def test_edge_command_parses_satchy_api_contract() -> None:
    command = EdgeCommand.model_validate(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "organization_id": "22222222-2222-2222-2222-222222222222",
            "site_id": "33333333-3333-3333-3333-333333333333",
            "edge_device_id": "44444444-4444-4444-4444-444444444444",
            "command_type": "radio_reply",
            "payload": {"text": "Control 2, Satchy. Go ahead.", "simulate_only": True},
            "priority": 100,
            "status": "dispatched",
            "created_at": datetime.now(UTC).isoformat(),
            "expires_at": None,
            "acknowledged_at": None,
            "completed_at": None,
        }
    )

    assert command.command_type == "radio_reply"
    assert command.payload["simulate_only"] is True
