from __future__ import annotations

import terrasatch_edge.entrypoint as entrypoint
from terrasatch_edge import __version__


class _FakeStream:
    def __init__(self, *, tty: bool) -> None:
        self.tty = tty
        self.calls: list[dict[str, str]] = []

    def isatty(self) -> bool:
        return self.tty

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_redirected_stdio_is_reconfigured_to_utf8(monkeypatch) -> None:
    stdout = _FakeStream(tty=False)
    stderr = _FakeStream(tty=False)
    monkeypatch.setattr(entrypoint.sys, "stdout", stdout)
    monkeypatch.setattr(entrypoint.sys, "stderr", stderr)

    entrypoint._configure_redirected_stdio()

    expected = [{"encoding": "utf-8", "errors": "replace"}]
    assert stdout.calls == expected
    assert stderr.calls == expected


def test_interactive_stdio_is_left_unchanged(monkeypatch) -> None:
    stdout = _FakeStream(tty=True)
    stderr = _FakeStream(tty=True)
    monkeypatch.setattr(entrypoint.sys, "stdout", stdout)
    monkeypatch.setattr(entrypoint.sys, "stderr", stderr)

    entrypoint._configure_redirected_stdio()

    assert stdout.calls == []
    assert stderr.calls == []


def test_version_flag_prints_package_version(capsys) -> None:
    entrypoint.main(["--version"])

    assert capsys.readouterr().out.strip() == f"terrasatch-edge {__version__}"


def test_short_version_flag_prints_package_version(capsys) -> None:
    entrypoint.main(["-V"])

    assert capsys.readouterr().out.strip() == f"terrasatch-edge {__version__}"
