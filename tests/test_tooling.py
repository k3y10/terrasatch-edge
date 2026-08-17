from __future__ import annotations

import os
from pathlib import Path

from terrasatch_edge.tooling import find_executable, probe_rtl_sdr


def test_find_executable_uses_terrasatch_tools_env(monkeypatch, tmp_path: Path) -> None:
    executable_name = "rtl_sdr.exe" if os.name == "nt" else "rtl_sdr"
    executable = tmp_path / executable_name
    executable.write_text("pilot", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.setenv("TERRASATCH_EDGE_TOOLS", str(tmp_path))

    assert find_executable("rtl_sdr") == executable


def test_find_executable_returns_none_for_unknown_tool() -> None:
    assert find_executable("terrasatch-tool-that-does-not-exist-7842") is None


def test_probe_default_sample_count_avoids_upstream_async_block_boundary(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    class Result:
        returncode = 1
        stdout = ""
        stderr = "probe"

    monkeypatch.setattr("terrasatch_edge.tooling.find_executable", lambda _: Path("rtl_sdr"))

    def fake_run(command: list[str], **_: object) -> Result:
        captured["command"] = command
        return Result()

    monkeypatch.setattr("terrasatch_edge.tooling.subprocess.run", fake_run)

    probe_rtl_sdr(timeout_seconds=1)

    command = captured["command"]
    sample_count = int(command[command.index("-n") + 1])
    default_block_bytes = 16 * 16_384
    requested_bytes = sample_count * 2

    assert requested_bytes % default_block_bytes != 0
