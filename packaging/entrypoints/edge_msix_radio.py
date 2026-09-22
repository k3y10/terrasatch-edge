from __future__ import annotations

from terrasatch_edge.entrypoint import main

from msix_common import configure_store_user_state


if __name__ == "__main__":
    configure_store_user_state()
    main(["radio", "start"])
