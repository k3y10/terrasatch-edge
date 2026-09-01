"""Safe API-to-Edge command processing for the simulation-only TX milestone."""

from __future__ import annotations

from dataclasses import dataclass, field

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
        failed = sum(outcome.result == "failed" for outcome in self.outcomes)
        if not self.polled:
            return "no Edge commands pending"
        detail = f"{self.polled} command(s) polled; {simulated} simulated"
        if failed:
            detail += f"; {failed} safely rejected"
        if self.errors:
            detail += f"; {len(self.errors)} retryable error(s)"
        return detail


def _result_for(command: EdgeCommand) -> tuple[str, str]:
    """Choose a result without invoking any radio, audio, or hardware provider."""

    if command.command_type != "radio_reply":
        return (
            "failed",
            f"Unsupported Edge command type '{command.command_type}'; no operation performed",
        )
    if command.payload.get("simulate_only") is not True:
        return (
            "failed",
            "radio_reply rejected because simulate_only was not explicitly true; no RF/PTT operation performed",
        )
    return (
        "simulated",
        "Simulation-only radio reply accepted; no RF/PTT operation was attempted",
    )


def process_edge_commands(
    client: TerraSatchApiClient,
    *,
    limit: int = 50,
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
            if command.status != "acknowledged":
                command = client.acknowledge_edge_command(command.id)
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
        except TerraSatchApiError as exc:
            cycle.errors.append(f"{command.id}: {exc}")
    return cycle
