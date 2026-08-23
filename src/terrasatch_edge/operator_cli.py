from __future__ import annotations

import ipaddress
import threading
import webbrowser
from typing import Annotated, Any

import typer
from rich.console import Console


console = Console()


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _launch_operator_console(
    host: str,
    port: int,
    *,
    open_browser: bool,
    allow_remote: bool,
) -> None:
    if not _is_loopback_host(host) and not allow_remote:
        console.print(
            "[red]Refusing to expose the Edge operator console beyond this computer.[/red]\n"
            "Use [bold]--allow-remote[/bold] only on a trusted, controlled network."
        )
        raise typer.Exit(2)

    try:
        import uvicorn
    except ImportError as exc:
        console.print(
            "[red]Operator UI dependencies are missing.[/red] "
            "Install the UI extra or use the packaged TerraSatch Edge build."
        )
        raise typer.Exit(2) from exc

    from .local_ui import build_app

    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"
    console.print(f"TerraSatch Edge Operator Console: [link={url}]{url}[/link]")
    console.print("Press Ctrl+C to stop the local console. The field agent/service can continue separately.")

    if open_browser:
        timer = threading.Timer(0.6, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    uvicorn.run(build_app(), host=host, port=port, log_level="warning")


def register_operator_commands(app: Any) -> None:
    @app.command("console")
    def operator_console(
        host: Annotated[str, typer.Option("--host", help="Local interface to bind.")] = "127.0.0.1",
        port: Annotated[int, typer.Option("--port", min=1, max=65535)] = 8742,
        no_browser: Annotated[
            bool,
            typer.Option("--no-browser", help="Do not automatically open the system browser."),
        ] = False,
        allow_remote: Annotated[
            bool,
            typer.Option(
                "--allow-remote",
                help="Allow a non-loopback bind. Use only on a trusted controlled network.",
            ),
        ] = False,
    ) -> None:
        """Open the guided local setup/configuration console."""
        _launch_operator_console(
            host,
            port,
            open_browser=not no_browser,
            allow_remote=allow_remote,
        )
