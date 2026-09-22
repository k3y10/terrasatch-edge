from __future__ import annotations

import os
from pathlib import Path

from terrasatch_edge.entrypoint import main


def _configure_windows_shared_state() -> None:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    root = program_data / "TerraSatch" / "Edge"
    os.environ.setdefault("TERRASATCH_EDGE_CONFIG_DIR", str(root))
    os.environ.setdefault("TERRASATCH_EDGE_STATE_DIR", str(root / "state"))
    os.environ.setdefault("TERRASATCH_EDGE_WINDOWS_CONSOLE", "1")


if __name__ == "__main__":
    _configure_windows_shared_state()
    main(["console"])
