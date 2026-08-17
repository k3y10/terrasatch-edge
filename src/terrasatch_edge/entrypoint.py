from __future__ import annotations

import sys

from . import __version__
from .cli import app


def main(argv: list[str] | None = None) -> None:
    """Launch the Edge CLI while supporting a conventional eager version flag."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--version"], ["-V"]):
        print(f"terrasatch-edge {__version__}")
        return

    if argv is None:
        app()
        return

    app(args=arguments, prog_name="terrasatch-edge")
