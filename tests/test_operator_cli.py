from __future__ import annotations

import pytest
import typer

import terrasatch_edge.operator_cli as operator_cli


def test_loopback_host_detection() -> None:
    assert operator_cli._is_loopback_host("127.0.0.1") is True
    assert operator_cli._is_loopback_host("::1") is True
    assert operator_cli._is_loopback_host("localhost") is True
    assert operator_cli._is_loopback_host("0.0.0.0") is False
    assert operator_cli._is_loopback_host("192.168.1.20") is False


def test_console_url_handles_ipv6() -> None:
    assert operator_cli._console_url("127.0.0.1", 8742) == "http://127.0.0.1:8742"
    assert operator_cli._console_url("::1", 8742) == "http://[::1]:8742"
    assert operator_cli._console_url("0.0.0.0", 8742) == "http://127.0.0.1:8742"


def test_remote_bind_requires_explicit_opt_in() -> None:
    with pytest.raises(typer.Exit) as exc:
        operator_cli._launch_operator_console(
            "0.0.0.0",
            8742,
            open_browser=False,
            allow_remote=False,
        )

    assert exc.value.exit_code == 2


def test_existing_console_is_reused(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(operator_cli, "_existing_console", lambda url: True)
    monkeypatch.setattr(operator_cli.webbrowser, "open", lambda url: opened.append(url))

    operator_cli._launch_operator_console(
        "127.0.0.1",
        8742,
        open_browser=True,
        allow_remote=False,
    )

    assert opened == ["http://127.0.0.1:8742"]
