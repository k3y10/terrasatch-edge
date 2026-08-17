from __future__ import annotations

import os
from pathlib import Path

from terrasatch_edge.tooling import find_executable


def test_find_executable_uses_terrasatch_tools_env(monkeypatch, tmp_path: Path) -> None:
    executable_name = "rtl_sdr.exe" if os.name == "nt" else "rtl_sdr"
    executable = tmp_path / executable_name
    executable.write_text("pilot", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.setenv("TERRASATCH_EDGE_TOOLS", str(tmp_path))

    assert find_executable("rtl_sdr") == executable


def test_find_executable_returns_none_for_unknown_tool() -> None:
    assert find_executable("terrasatch-tool-that-does-not-exist-7842") is None
