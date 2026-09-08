"""Safe API-to-Edge command processing for the simulation-only TX milestone."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .config import EdgeConfig
from .radio_providers import RadioTxProvider, SimulationRadioProvider, rf_execution_blocker
from .radio_execution import execute_radio_reply

from .api import TerraSatchApiClient, TerraSatchApiError
from .models import EdgeCommand


@dataclass(frozen=True)
class CommandOutcome:
    command_id: str
    command_type: str
    result: str
    detail: str


@dataclass
class CommandCycle:
    polled: int = 0
    outcomes: list[CommandOutcome] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    poll_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.poll_error is None and not self.errors

    def summary(self) -> str:
        if self.poll_error:
            return f"command polling unavailable: {self.poll_error}"
        simulated = sum(outcome.result == "simulated" for outcome in self.outcomes)
        transmitted = sum(outcome.result == "transmitted" for outcome in self.outcomes)
        failed = sum(outcome.result == "failed" for outcome in self.outcomes)
        if not self.polled:
            return "no Edge commands pending"
        detail = f"{self.polled} command(s) polled; {simulated} simulated"
        if transmitted:
            detail += f"; {transmitted} transmitted"
        if failed:
            detail += f"; {failed} safely rejected"
        if self.errors:
            detail += f"; {len(self.errors)} retryable error(s)"
        return detail


def _result_for(command: EdgeCommand) -> tuple[str, str]:
    """Choose a result without invoking any radio, audio, or hardware provider."""

    if command.expires_at is not None:
        if command.expires_at.utcoffset() is None or command.expires_at <= datetime.now(UTC):
            return "failed", "Expired or timezone-ambiguous command; no operation performed"
    if command.status != "acknowledged":
        return "failed", "Command is not acknowledged; no operation performed"
    if command.command_type != "radio_reply":
        return (
            "failed",
            f"Unsupported Edge command type '{command.command_type}'; no operation performed",
        )
    if command.payload.get("simulate_only") is not True:
        return (
            "failed",
            "radio_reply rejected because simulate_only was not explicitly true. " + rf_execution_blocker(),
        )
    if command.payload.get("reply_route") not in (None, "simulation"):
        return "failed", "Conflicting simulation and reply route; no operation performed"
    text = command.payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return "failed", "Radio reply text is missing; no operation performed"
    return SimulationRadioProvider().simulate()


def process_edge_commands(
    client: TerraSatchApiClient,
    *,
    limit: int = 50,
    config: EdgeConfig | None = None,
    remote_config: dict | None = None,
    provider: RadioTxProvider | None = None,
) -> CommandCycle:
    """Poll, ACK, and terminally report device-owned commands one at a time.

    Acknowledged commands are safe to replay. The API keeps them pollable until a
    terminal result arrives, so a process or network failure between ACK and result
    does not strand an outbound action.
    """

    cycle = CommandCycle()
    try:
        commands = client.edge_commands(limit=limit)
    except TerraSatchApiError as exc:
        cycle.poll_error = str(exc)
        return cycle

    cycle.polled = len(commands)
    for command in commands:
        try:
            original = command
            if config is not None and (
                not config.device_id or not config.site_id or not config.organization_id
                or command.edge_device_id != config.device_id
                or command.site_id != config.site_id
                or command.organization_id != config.organization_id
            ):
                cycle.errors.append(f"{command.id}: Command does not match paired identity")
                continue
            if command.status not in {"queued", "dispatched", "acknowledged"}:
                cycle.errors.append(f"{command.id}: Command is already terminal or invalid")
                continue
            if command.status != "acknowledged":
                command = client.acknowledge_edge_command(command.id)
            if (command.id, command.edge_device_id, command.site_id, command.organization_id,
                command.command_type, command.payload) != (
                original.id, original.edge_device_id, original.site_id, original.organization_id,
                original.command_type, original.payload
            ):
                cycle.errors.append(f"{original.id}: ACK returned a different command")
                continue
            if command.payload.get("simulate_only") is False and command.command_type == "radio_reply" and config is not None:
                if command.status != "acknowledged":
                    raise ValueError("RF command is not acknowledged")
                result, detail = execute_radio_reply(
                    command, client=client, config=config,
                    remote_config=remote_config or {}, provider=provider,
                )
            else:
                result, detail = _result_for(command)
            client.report_edge_command_result(
                command.id,
                status=result,
                detail=detail,
            )
            cycle.outcomes.append(
                CommandOutcome(
                    command_id=command.id,
                    command_type=command.command_type,
                    result=result,
                    detail=detail,
                )
            )
        except (TerraSatchApiError, ValueError, RuntimeError, OSError) as exc:
            cycle.errors.append(f"{command.id}: {exc}")
    return cycle
