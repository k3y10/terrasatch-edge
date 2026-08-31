from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import pytest

from terrasatch_edge.api import TerraSatchApiError
from terrasatch_edge.commands import process_edge_commands
from terrasatch_edge.models import EdgeCommand


def _command(
    *,
    command_type: str = "radio_reply",
    simulate_only: bool | None = True,
    status: str = "dispatched",
) -> EdgeCommand:
    payload: dict[str, Any] = {"text": "Control 2, Satchy. Go ahead."}
    if simulate_only is not None:
        payload["simulate_only"] = simulate_only
    return EdgeCommand.model_validate(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "organization_id": "22222222-2222-2222-2222-222222222222",
            "site_id": "33333333-3333-3333-3333-333333333333",
            "edge_device_id": "44444444-4444-4444-4444-444444444444",
            "command_type": command_type,
            "payload": payload,
            "priority": 100,
            "status": status,
            "created_at": "2026-08-31T12:00:00Z",
        }
    )


class FakeCommandClient:
    def __init__(self, command: EdgeCommand, *, fail_first_result: bool = False) -> None:
        self.command = command
        self.fail_first_result = fail_first_result
        self.acks: list[str] = []
        self.results: list[tuple[str, str, str | None]] = []

    def edge_commands(self, *, limit: int = 50) -> list[EdgeCommand]:
        assert 1 <= limit <= 100
        return [self.command]

    def acknowledge_edge_command(self, command_id: str) -> EdgeCommand:
        self.acks.append(command_id)
        self.command = self.command.model_copy(update={"status": "acknowledged"})
        return self.command

    def report_edge_command_result(
        self,
        command_id: str,
        *,
        status: str,
        detail: str | None = None,
    ) -> EdgeCommand:
        self.results.append((command_id, status, detail))
        if self.fail_first_result and len(self.results) == 1:
            raise TerraSatchApiError("temporary network failure")
        self.command = self.command.model_copy(update={"status": "completed"})
        return self.command


def test_radio_reply_is_acknowledged_and_simulated_without_hardware() -> None:
    client = FakeCommandClient(_command())

    cycle = process_edge_commands(client)  # type: ignore[arg-type]

    assert cycle.ok is True
    assert client.acks == [client.command.id]
    assert client.results[0][1] == "simulated"
    assert "no RF/PTT operation" in (client.results[0][2] or "")
    assert cycle.outcomes[0].result == "simulated"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (_command(simulate_only=False), "simulate_only"),
        (_command(simulate_only=None), "simulate_only"),
        (_command(command_type="radio_tx"), "Unsupported"),
        (_command(command_type="diagnostic"), "Unsupported"),
    ],
)
def test_non_simulated_or_unsupported_commands_are_safely_failed(
    command: EdgeCommand,
    expected: str,
) -> None:
    client = FakeCommandClient(command)

    cycle = process_edge_commands(client)  # type: ignore[arg-type]

    assert cycle.ok is True
    assert client.results[0][1] == "failed"
    assert expected in (client.results[0][2] or "")
    assert cycle.outcomes[0].result == "failed"


def test_acknowledged_command_resumes_result_without_duplicate_ack() -> None:
    client = FakeCommandClient(_command(status="acknowledged"))

    cycle = process_edge_commands(client)  # type: ignore[arg-type]

    assert cycle.ok is True
    assert client.acks == []
    assert [result[1] for result in client.results] == ["simulated"]


def test_temporary_result_failure_is_retried_from_acknowledged_state() -> None:
    client = FakeCommandClient(_command(), fail_first_result=True)

    first = process_edge_commands(client)  # type: ignore[arg-type]
    second = process_edge_commands(client)  # type: ignore[arg-type]

    assert first.ok is False
    assert second.ok is True
    assert len(client.acks) == 1
    assert [result[1] for result in client.results] == ["simulated", "simulated"]


def test_poll_failure_is_reported_without_touching_hardware() -> None:
    class OfflineClient:
        def edge_commands(self, *, limit: int = 50) -> list[EdgeCommand]:
            raise TerraSatchApiError("API unavailable")

    cycle = process_edge_commands(OfflineClient())  # type: ignore[arg-type]

    assert cycle.ok is False
    assert cycle.polled == 0
    assert cycle.poll_error == "API unavailable"


def test_real_http_cycle_polls_acknowledges_and_reports_simulated() -> None:
    state: dict[str, Any] = {
        "command": _command().model_dump(mode="json"),
        "requests": [],
        "result": None,
    }

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            state["requests"].append(("GET", self.path, self.headers.get("Authorization")))
            self._respond([state["command"]])

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            state["requests"].append(("POST", path, self.headers.get("Authorization")))
            command = dict(state["command"])
            if path.endswith("/ack"):
                command["status"] = "acknowledged"
            elif path.endswith("/result"):
                length = int(self.headers.get("Content-Length", "0"))
                result = json.loads(self.rfile.read(length))
                state["result"] = result
                command["status"] = "completed"
            state["command"] = command
            self._respond(command)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        from terrasatch_edge.api import TerraSatchApiClient

        client = TerraSatchApiClient(f"http://{host}:{port}", "paired-key", timeout=2)
        cycle = process_edge_commands(client)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert cycle.ok is True
    assert [request[0] for request in state["requests"]] == ["GET", "POST", "POST"]
    assert all(request[2] == "Bearer paired-key" for request in state["requests"])
    assert state["result"]["status"] == "simulated"
    assert "no RF/PTT operation" in state["result"]["detail"]
