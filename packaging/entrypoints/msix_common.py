from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from collections.abc import Sequence


def configure_store_user_state() -> dict[str, str]:
    """Keep all Store/MSIX Edge processes in one writable per-user state root."""
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    root = local_app_data / "TerraSatch" / "Edge"
    env = os.environ.copy()
    env.setdefault("TERRASATCH_EDGE_CONFIG_DIR", str(root))
    env.setdefault("TERRASATCH_EDGE_STATE_DIR", str(root / "state"))
    return env


def run_packaged_edge(args: Sequence[str], *, console: bool = False) -> int:
    launcher = Path(sys.executable).resolve()
    edge_exe = launcher.parent / "Edge" / "TerraSatchEdge.exe"
    if not edge_exe.is_file():
        raise SystemExit(f"TerraSatch Edge runtime not found: {edge_exe}")

    env = configure_store_user_state()
    if console:
        env.setdefault("TERRASATCH_EDGE_WINDOWS_CONSOLE", "1")

    completed = subprocess.run([str(edge_exe), *args], env=env, check=False)
    return completed.returncode
