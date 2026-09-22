from __future__ import annotations

import os
from pathlib import Path


def configure_store_user_state() -> None:
    """Keep all Store/MSIX Edge processes in one writable per-user state root."""
    local_app_data = Path(
        os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
    )
    root = local_app_data / "TerraSatch" / "Edge"
    os.environ.setdefault("TERRASATCH_EDGE_CONFIG_DIR", str(root))
    os.environ.setdefault("TERRASATCH_EDGE_STATE_DIR", str(root / "state"))
