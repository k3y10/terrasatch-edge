from __future__ import annotations

import os

from terrasatch_edge.entrypoint import main

from msix_common import configure_store_user_state


if __name__ == "__main__":
    configure_store_user_state()
    os.environ.setdefault("TERRASATCH_EDGE_WINDOWS_CONSOLE", "1")
    main(["console"])
