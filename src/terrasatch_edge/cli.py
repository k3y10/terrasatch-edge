from __future__ import annotations

import getpass
import json
import platform
import socket
import sys
import uuid
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .agent import EdgeAgent
from .api import TerraSatchApiClient, TerraSatchApiError
from .config import EdgeConfig, clear_api_key, get_paths, load_api_key, load_config, save_api_key, save_config
from .discovery import save_snapshot, scan_hardware
from .doctor import run_doctor
from .models import DeviceKind, HardwareDevice

app = typer.Typer(no_args_is_help=True, help="TerraSatch Edge local setup and field-device agent.")
console = Console()


def _header() -> None:
    console.print(
        Panel.fit(
            "[bold]TerraSatch Edge[/bold]\n[dim]LISTEN · WATCH · LEARN · ADAPT[/dim]",
            border_style="green",
        )
    )


def _human_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    current = float(value)
    for unit in units:
        if current < 1024 or unit == units[-1]:
            return f"{current:.1f} {unit}"
        current /= 1024
    return str(value)


def _device_table(devices: list[HardwareDevice]) -> Table:
    table = Table(title="Detected hardware", show_lines=False)
    table.add_column("Type", style="cyan")
    table.add_column("Device")
    table.add_column("ID / Path", overflow="fold")
    table.add_column("Capabilities", overflow="fold")
    for device in devices:
        table.add_row(
            device.kind.value,
            device.name,
            device.path or device.identifier,
            ", ".join(device.capabilities) or "—",
        )
    return table


@app.command()
def version() -> None:
    """Show the installed TerraSatch Edge version."""
    console.print(f"terrasatch-edge {__version__}")


@app.command()
def scan(
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON instead of a table.")] = False,
    no_network: Annotated[bool, typer.Option("--no-network", help="Exclude network interfaces.")] = False,
) -> None:
    """Scan this machine for hardware TerraSatch Edge can use or inspect."""
    snapshot = scan_hardware(include_network=not no_network)
    path = save_snapshot(snapshot)
    if json_output:
        console.print(snapshot.model_dump_json(indent=2))
        return
    _header()
    console.print(
        f"[bold]{snapshot.hostname}[/bold] · {snapshot.platform} {snapshot.platform_release} · "
        f"{snapshot.architecture}\n"
        f"CPU threads: {snapshot.cpu_count_logical or 'unknown'} · "
        f"RAM: {_human_bytes(snapshot.memory_total_bytes)} · "
        f"Free disk: {_human_bytes(snapshot.disk_free_bytes)}"
    )
    console.print(_device_table(snapshot.devices))
    console.print(f"[dim]Snapshot saved to {path}[/dim]")


@app.command()
def devices() -> None:
    """List recognized non-network field hardware."""
    snapshot = scan_hardware(include_network=False)
    filtered = [d for d in snapshot.devices if d.kind != DeviceKind.SYSTEM]
    console.print(_device_table(filtered))


@app.command()
def setup(
    api_url: Annotated[str | None, typer.Option("--api-url", help="TerraSatch API base URL.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="Service API key; omit to enter securely.")] = None,
    site_id: Annotated[str | None, typer.Option("--site-id", help="Preselect a TerraSatch site UUID.")] = None,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Fail instead of prompting for missing values.")
    ] = False,
) -> None:
    """Run the TerraSatch Edge setup wizard."""
    _header()
    current = load_config()
    selected_api = (api_url or current.api_url).rstrip("/")

    if not non_interactive:
        selected_api = typer.prompt("TerraSatch API", default=selected_api).rstrip("/")

    console.print("\n[bold]1. Checking API[/bold]")
    anonymous_client = TerraSatchApiClient(selected_api)
    try:
        health = anonymous_client.health()
        console.print(f"[green]✓[/green] API reachable: {health.get('status', 'ok')}")
    except TerraSatchApiError as exc:
        console.print(f"[red]✗[/red] API check failed: {exc}")
        if non_interactive:
            raise typer.Exit(2)
        if not typer.confirm("Save configuration anyway?", default=False):
            raise typer.Exit(2)

    console.print("\n[bold]2. Scanning local hardware[/bold]")
    snapshot = scan_hardware(include_network=False)
    save_snapshot(snapshot)
    console.print(_device_table(snapshot.devices))

    console.print("\n[bold]3. Authenticating[/bold]")
    key = api_key or load_api_key()
    if not key and not non_interactive:
        key = getpass.getpass("TerraSatch service API key (input hidden): ").strip()
    if not key:
        console.print("[red]No API key supplied.[/red]")
        raise typer.Exit(2)

    client = TerraSatchApiClient(selected_api, key)
    try:
        identity = client.identity()
        console.print("[green]✓[/green] API key accepted")
        org_name = (
            identity.raw.get("organization_name")
            or identity.raw.get("organization", {}).get("name")
            if isinstance(identity.raw.get("organization"), dict)
            else None
        )
        if org_name:
            console.print(f"Organization: [bold]{org_name}[/bold]")
    except TerraSatchApiError as exc:
        console.print(f"[red]✗ Authentication failed:[/red] {exc}")
        raise typer.Exit(3) from exc

    console.print("\n[bold]4. Selecting site[/bold]")
    selected_site_id = site_id or current.site_id
    selected_site_name = current.site_name
    try:
        sites = [site for site in client.sites() if site.enabled]
    except TerraSatchApiError as exc:
        sites = []
        console.print(f"[yellow]Could not list sites:[/yellow] {exc}")

    if selected_site_id:
        match = next((site for site in sites if site.id == selected_site_id), None)
        if match:
            selected_site_name = match.name
            console.print(f"Using site: [bold]{match.name}[/bold] ({match.id})")
    elif sites and not non_interactive:
        for index, site in enumerate(sites, start=1):
            console.print(f"  {index}. {site.name} ({site.id})")
        choice = typer.prompt("Select site", default="1")
        try:
            selected = sites[int(choice) - 1]
        except (ValueError, IndexError):
            console.print("[red]Invalid site selection.[/red]")
            raise typer.Exit(2)
        selected_site_id = selected.id
        selected_site_name = selected.name
    elif len(sites) == 1:
        selected_site_id = sites[0].id
        selected_site_name = sites[0].name
    elif not selected_site_id:
        console.print("[yellow]No site selected. Edge can be configured again after a site exists.[/yellow]")

    node_name = current.node_name or f"{socket.gethostname()}-edge"
    if not non_interactive:
        node_name = typer.prompt("Edge node name", default=node_name)

    config = EdgeConfig(
        api_url=selected_api,
        site_id=selected_site_id,
        site_name=selected_site_name,
        node_name=node_name,
        scan_interval_seconds=current.scan_interval_seconds,
        source=current.source,
    )
    config_path = save_config(config)
    credential_path = save_api_key(key)

    console.print("\n[bold green]✓ TerraSatch Edge configured[/bold green]")
    console.print(f"Node: [bold]{node_name}[/bold]")
    console.print(f"API: {selected_api}")
    console.print(f"Site: {selected_site_name or selected_site_id or 'not selected'}")
    console.print(f"Config: {config_path}")
    console.print(f"Credentials: {credential_path}")
    console.print("\nNext: [bold]terrasatch-edge doctor[/bold]")


@app.command()
def status(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show local Edge configuration, API connectivity, and hardware status."""
    config = load_config()
    key = load_api_key()
    client = TerraSatchApiClient(config.api_url, key)
    api_online = False
    authenticated = False
    details: dict[str, object] = {}
    try:
        details["health"] = client.health()
        api_online = True
    except TerraSatchApiError as exc:
        details["health_error"] = str(exc)
    if key and api_online:
        try:
            details["identity"] = client.identity().raw
            authenticated = True
        except TerraSatchApiError as exc:
            details["auth_error"] = str(exc)

    snapshot = scan_hardware(include_network=False)
    result = {
        "version": __version__,
        "node_name": config.node_name,
        "hostname": snapshot.hostname,
        "api_url": config.api_url,
        "api_online": api_online,
        "authenticated": authenticated,
        "site_id": config.site_id,
        "site_name": config.site_name,
        "device_count": len(snapshot.devices),
        "details": details,
    }
    if json_output:
        console.print_json(json.dumps(result, default=str))
        return

    _header()
    console.print(f"Node: [bold]{config.node_name or snapshot.hostname}[/bold]")
    console.print(f"API: {'[green]ONLINE[/green]' if api_online else '[red]OFFLINE[/red]'} · {config.api_url}")
    console.print(f"Auth: {'[green]OK[/green]' if authenticated else '[yellow]NOT READY[/yellow]'}")
    console.print(f"Site: {config.site_name or config.site_id or '[yellow]not selected[/yellow]'}")
    console.print(f"Detected hardware records: {len(snapshot.devices)}")


@app.command()
def doctor() -> None:
    """Diagnose API, credentials, SDR, GPS, audio, and local setup issues."""
    _header()
    checks = run_doctor()
    table = Table(title="TerraSatch Edge diagnostics")
    table.add_column("Result")
    table.add_column("Check")
    table.add_column("Detail")
    table.add_column("Recommendation")
    failures = 0
    for check in checks:
        if check.ok:
            marker = "[green]✓[/green]"
        else:
            marker = "[yellow]![/yellow]"
            failures += 1
        table.add_row(marker, check.name, check.detail, check.recommendation or "—")
    console.print(table)
    if failures:
        console.print(f"[yellow]{failures} diagnostic item(s) need attention or are optional hardware gaps.[/yellow]")


@app.command("ingest-text")
def ingest_text(
    text: Annotated[str, typer.Argument(help="Text/radio-style message to send to TerraSatch.")],
    callsign: Annotated[str | None, typer.Option("--callsign")] = None,
    site_id: Annotated[str | None, typer.Option("--site-id")] = None,
    source_message_id: Annotated[str | None, typer.Option("--source-message-id")] = None,
) -> None:
    """Send a test transmission through the live TerraSatch API ingestion path."""
    config = load_config()
    key = load_api_key()
    target_site = site_id or config.site_id
    if not key:
        console.print("[red]No API key configured. Run `terrasatch-edge setup`.[/red]")
        raise typer.Exit(2)
    if not target_site:
        console.print("[red]No site selected. Run setup again or use --site-id.[/red]")
        raise typer.Exit(2)
    message_id = source_message_id or f"edge-{platform.node()}-{uuid.uuid4()}"
    client = TerraSatchApiClient(config.api_url, key)
    try:
        response = client.ingest_text(
            site_id=target_site,
            text=text,
            callsign=callsign,
            source_message_id=message_id,
            source=config.source,
        )
    except TerraSatchApiError as exc:
        console.print(f"[red]Ingestion failed:[/red] {exc}")
        raise typer.Exit(3) from exc
    console.print("[green]✓ Transmission accepted[/green]")
    console.print_json(json.dumps(response, default=str))


@app.command()
def run(once: Annotated[bool, typer.Option("--once", help="Run one agent cycle and exit.")] = False) -> None:
    """Run the local Edge agent and persist hardware snapshots while checking API health."""
    agent = EdgeAgent()
    if once:
        ok, message = agent.tick()
        console.print(f"{'[green]✓[/green]' if ok else '[yellow]![/yellow]'} {message}")
        return

    _header()
    console.print("Edge agent running. Press Ctrl+C to stop.")

    def on_tick(ok: bool, message: str) -> None:
        console.print(f"{'[green]✓[/green]' if ok else '[yellow]![/yellow]'} {message}")

    agent.run_forever(on_tick=on_tick)


@app.command()
def ui(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8742,
) -> None:
    """Launch the optional local TerraSatch Edge status interface."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print("[red]UI dependencies missing.[/red] Install with: pip install 'terrasatch-edge[ui]'")
        raise typer.Exit(2) from exc
    from .local_ui import build_app

    console.print(f"Opening local Edge interface at http://{host}:{port}")
    uvicorn.run(build_app(), host=host, port=port, log_level="warning")


@app.command("logout")
def logout() -> None:
    """Remove the locally stored TerraSatch Edge API key."""
    clear_api_key()
    console.print("[green]Local TerraSatch Edge credentials removed.[/green]")


@app.command("paths")
def show_paths() -> None:
    """Show local configuration/state file locations."""
    paths = get_paths()
    console.print(f"Config: {paths.config_file}")
    console.print(f"Credentials: {paths.credentials_file}")
    console.print(f"Snapshot: {paths.snapshot_file}")


if __name__ == "__main__":
    app()
