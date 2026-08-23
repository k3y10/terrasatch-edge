from __future__ import annotations

import sys

from . import __version__
from .cli import app
from .operator_cli import register_operator_commands
from .speech_cli import register_speech_commands

register_speech_commands(app)
register_operator_commands(app)


def _configure_redirected_stdio() -> None:
    """Use UTF-8 for redirected native-service output without changing interactive terminals."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue

        isatty = getattr(stream, "isatty", None)
        try:
            if callable(isatty) and isatty():
                continue
        except OSError:
            pass

        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # Some frozen/redirected stream implementations do not permit
            # runtime reconfiguration. The WinSW environment remains a
            # secondary UTF-8 safeguard for those cases.
            pass


def main(argv: list[str] | None = None) -> None:
    """Launch the Edge CLI while supporting a conventional eager version flag."""

    _configure_redirected_stdio()

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["--version"], ["-V"]):
        print(f"terrasatch-edge {__version__}")
        return

    if argv is None:
        app()
        return

    app(args=arguments, prog_name="terrasatch-edge")
