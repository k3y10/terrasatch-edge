from __future__ import annotations

from datetime import UTC, datetime

from terrasatch_edge.models import PairingClaim, PairingStart


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
