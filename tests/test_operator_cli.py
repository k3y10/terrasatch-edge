from __future__ import annotations

import pytest
import typer

from terrasatch_edge.operator_cli import _is_loopback_host, _launch_operator_console


def test_loopback_host_detection() -> None:
    assert _is_loopback_host("127.0.0.1") is True
    assert _is_loopback_host("::1") is True
    assert _is_loopback_host("localhost") is True
    assert _is_loopback_host("0.0.0.0") is False
    assert _is_loopback_host("192.168.1.20") is False


def test_remote_bind_requires_explicit_opt_in() -> None:
    with pytest.raises(typer.Exit) as exc:
        _launch_operator_console(
            "0.0.0.0",
            8742,
            open_browser=False,
            allow_remote=False,
        )

    assert exc.value.exit_code == 2
