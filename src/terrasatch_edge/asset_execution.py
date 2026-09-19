"""Execute policy-gated typed field missions through installed provider adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from .asset_providers import AssetMission, FieldAssetProvider
from .config import EdgeConfig, get_paths
from .effect_journal import EffectJournal
from .models import EdgeCommand


def execute_asset_mission(
    command: EdgeCommand,
    *,
    config: EdgeConfig,
    remote_config: dict,
    providers: dict[str, FieldAssetProvider] | None,
) -> tuple[str, str]:
    payload = command.payload
    deadline = command.expires_at
    if deadline is None or deadline.utcoffset() is None or deadline <= datetime.now(UTC):
        return "failed", "Field mission requires a future timezone-aware deadline"
    if command.status != "acknowledged":
        return "failed", "Field mission must be acknowledged before execution"

    for key in ("mission_id", "asset_id"):
        try:
            UUID(str(payload[key]))
        except (ValueError, TypeError, KeyError, AttributeError):
            return "failed", f"Field mission requires a valid {key}"

    provider_name = payload.get("provider")
    mission_type = payload.get("mission_type")
    objective = payload.get("objective")
    required = payload.get("required_capabilities")
    target = payload.get("target")
    parameters = payload.get("parameters")
    if not isinstance(provider_name, str) or not provider_name.strip():
        return "failed", "Field mission provider is missing"
    if not isinstance(mission_type, str) or not mission_type.strip():
        return "failed", "Field mission type is missing"
    if not isinstance(objective, str) or not objective.strip():
        return "failed", "Field mission objective is missing"
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        return "failed", "Field mission capabilities are invalid"
    if not isinstance(target, dict) or not isinstance(parameters, dict):
        return "failed", "Field mission target or parameters are invalid"

    assets = remote_config.get("assets")
    if not isinstance(assets, dict) or assets.get("execution_enabled") is not True:
        return "failed", "Local field-asset execution policy is disabled"
    bindings = assets.get("bindings")
    if not isinstance(bindings, dict):
        return "failed", "Field-asset bindings are not configured"
    binding = bindings.get(str(payload["asset_id"]))
    if not isinstance(binding, dict) or binding.get("enabled") is not True:
        return "failed", "Field asset is not enabled on this Edge node"
    if binding.get("provider") != provider_name:
        return "failed", "Field asset provider binding does not match mission"
    allowed_types = binding.get("allowed_mission_types", [])
    if not isinstance(allowed_types, list) or mission_type not in allowed_types:
        return "failed", "Field mission type is not authorized for this asset"

    provider = (providers or {}).get(provider_name)
    if provider is None:
        return "failed", "Configured field-asset provider is not installed"
    try:
        status = provider.status(str(payload["asset_id"]))
    except Exception as exc:
        return "failed", f"Field-asset readiness check failed ({type(exc).__name__})"
    if not status.ready:
        return "failed", "Field asset provider is not ready"
    required_set = {item.casefold() for item in required}
    reported = {item.casefold() for item in status.capabilities}
    if not required_set <= reported:
        return "failed", "Field asset provider lacks required mission capabilities"

    scope = "|".join(
        [
            config.api_url,
            command.organization_id,
            command.site_id,
            command.edge_device_id,
            str(payload["asset_id"]),
        ]
    )
    journal = EffectJournal(get_paths().state_dir / "asset-command-journal.sqlite3")
    previous = journal.previous(scope, command)
    if previous is not None:
        return previous
    if not journal.claim(scope, command):
        previous = journal.previous(scope, command)
        if previous is None:
            raise RuntimeError("Field mission execution claim unavailable")
        return previous
    if deadline <= datetime.now(UTC):
        outcome = ("failed", "Field mission deadline elapsed before provider execution")
        journal.finish(scope, command, outcome)
        return outcome

    mission = AssetMission(
        command_id=command.id,
        mission_id=str(payload["mission_id"]),
        asset_id=str(payload["asset_id"]),
        mission_type=mission_type,
        objective=objective,
        target=target,
        parameters=parameters,
    )
    try:
        provider.execute(mission)
        outcome = ("completed", "Provider accepted and completed the typed field mission")
    except Exception as exc:
        outcome = (
            "failed",
            f"Field mission failed or outcome is uncertain ({type(exc).__name__}); will not replay",
        )
    journal.finish(scope, command, outcome)
    return outcome
