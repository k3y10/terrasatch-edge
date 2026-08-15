from __future__ import annotations

import json
import platform
import socket
import time
import uuid
import webbrowser
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .agent import EdgeAgent
from .api import TerraSatchApiClient, TerraSatchApiError
from .config import (
    EdgeConfig,
    clear_api_key,
    get_paths,
    load_api_key,
    load_config,
    load_remote_config,
    save_api_key,
    save_config,
)
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


def _pair_device(
    api_url: str,
    node_name: str,
    *,
    open_browser: bool,
) -> tuple[str, dict[str, object]]:
    snapshot = scan_hardware(include_network=False)
    client = TerraSatchApiClient(api_url)
    pairing = client.start_pairing(
        name=node_name,
        hostname=snapshot.hostname,
        platform_name=snapshot.platform,
        architecture=snapshot.architecture,
    )

    console.print("\n[bold]Pair this Edge node[/bold]")
    console.print(Panel.fit(f"[bold]{pairing.user_code}[/bold]", border_style="green"))
    console.print(f"Open: [link={pairing.verification_url}]{pairing.verification_url}[/link]")
    console.print(
        "Approve the organization and site in TerraSatch Admin. "
        "This window will continue automatically."
    )

    if open_browser:
        try:
            webbrowser.open(pairing.verification_url)
        except Exception:
            pass

    deadline = pairing.expires_at
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)

    while datetime.now(UTC) < deadline:
        claim = client.claim_pairing(pairing.device_code)
        if claim.status == "approved" and claim.token and claim.device:
            return claim.token, claim.device.model_dump(mode="json")
        if claim.status in {"expired", "claimed"}:
            raise TerraSatchApiError(f"Pairing ended with status: {claim.status}")
        time.sleep(max(2, pairing.interval_seconds))

    raise TerraSatchApiError("Pairing code expired before it was approved")


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
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="Advanced/manual service key fallback; pairing is preferred."),
    ] = None,
    site_id: Annotated[str | None, typer.Option("--site-id", help="Manual-key mode site UUID.")] = None,
    non_interactive: Annotated[
        bool, typer.Option("--non-interactive", help="Do not prompt for editable values.")
    ] = False,
    no_browser: Annotated[
        bool, typer.Option("--no-browser", help="Print the pairing URL without opening a browser.")
    ] = False,
) -> None:
    """Pair this computer to TerraSatch, scan hardware, and save its device credential."""
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
        raise typer.Exit(2) from exc

    console.print("\n[bold]2. Scanning local hardware[/bold]")
    snapshot = scan_hardware(include_network=False)
    save_snapshot(snapshot)
    console.print(_device_table(snapshot.devices))

    node_name = current.node_name or f"{socket.gethostname()}-edge"
    if not non_interactive:
        node_name = typer.prompt("Edge node name", default=node_name)

    key = api_key
    device_payload: dict[str, object] = {}
    selected_site_id = site_id
    selected_site_name = current.site_name

    if not key:
        console.print("\n[bold]3. Pairing device[/bold]")
        try:
            key, device_payload = _pair_device(
                selected_api,
                node_name,
                open_browser=not no_browser,
            )
        except TerraSatchApiError as exc:
            console.print(f"[red]✗ Pairing failed:[/red] {exc}")
            raise typer.Exit(3) from exc
        selected_site_id = str(device_payload.get("site_id") or "") or None
        console.print("[green]✓[/green] Device approved and credential issued")
    else:
        console.print("\n[bold]3. Manual credential fallback[/bold]")
        client = TerraSatchApiClient(selected_api, key)
        try:
            client.identity()
        except TerraSatchApiError as exc:
            console.print(f"[red]✗ Authentication failed:[/red] {exc}")
            raise typer.Exit(3) from exc
        if not selected_site_id:
            sites = [site for site in client.sites() if site.enabled]
            if len(sites) == 1:
                selected_site_id = sites[0].id
                selected_site_name = sites[0].name
            elif sites and not non_interactive:
                for index, site in enumerate(sites, start=1):
                    console.print(f"  {index}. {site.name} ({site.id})")
                choice = typer.prompt("Select site", default="1")
                try:
                    selected = sites[int(choice) - 1]
                except (ValueError, IndexError):
                    raise typer.Exit(2)
                selected_site_id = selected.id
                selected_site_name = selected.name

    if not key:
        raise typer.Exit(3)

    config = EdgeConfig(
        api_url=selected_api,
        device_id=str(device_payload.get("id") or "") or current.device_id,
        organization_id=str(device_payload.get("organization_id") or "") or current.organization_id,
        site_id=selected_site_id,
        site_name=selected_site_name,
        node_name=node_name,
        scan_interval_seconds=current.scan_interval_seconds,
        source=current.source,
    )
    config_path = save_config(config)
    credential_path = save_api_key(key)

    console.print("\n[bold]4. Sending first heartbeat[/bold]")
    paired_client = TerraSatchApiClient(selected_api, key)
    try:
        heartbeat = paired_client.heartbeat(snapshot)
        console.print("[green]✓[/green] Hardware inventory synced")
        device = heartbeat.get("device", {})
        if isinstance(device, dict) and device.get("id"):
            config.device_id = str(device["id"])
            config.organization_id = str(device.get("organization_id") or config.organization_id or "") or None
            config.site_id = str(device.get("site_id") or config.site_id or "") or None
            save_config(config)
    except TerraSatchApiError as exc:
        console.print(f"[yellow]! Initial heartbeat not accepted:[/yellow] {exc}")

    console.print("\n[bold green]✓ TerraSatch Edge configured[/bold green]")
    console.print(f"Node: [bold]{node_name}[/bold]")
    console.print(f"Device: {config.device_id or 'manual credential'}")
    console.print(f"API: {selected_api}")
    console.print(f"Site: {config.site_name or config.site_id or 'not selected'}")
    console.print(f"Config: {config_path}")
    console.print(f"Credentials: {credential_path}")
    console.print("\nNext: [bold]terrasatch-edge doctor[/bold]")


@app.command()
def status(json_output: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show local Edge configuration, API connectivity, pairing and hardware status."""
    config = load_config()
    key = load_api_key()
    client = TerraSatchApiClient(config.api_url, key)
    api_online = False
    authenticated = False
    details: dict[str, object] = {"remote_config": load_remote_config()}
    try:
        details["health"] = client.health()
        api_online = True
    except TerraSatchApiError as exc:
        details["health_error"] = str(exc)
    if key and api_online:
        try:
            details["edge"] = client.edge_me().model_dump(mode="json")
            authenticated = True
        except TerraSatchApiError as exc:
            try:
                details["identity"] = client.identity().raw
                authenticated = True
            except TerraSatchApiError:
                details["auth_error"] = str(exc)

    snapshot = scan_hardware(include_network=False)
    result = {
        "version": __version__,
        "device_id": config.device_id,
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
    console.print(f"Device ID: {config.device_id or '[yellow]not paired[/yellow]'}")
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
        console.print("[red]No Edge credential configured. Run `terrasatch-edge setup`.[/red]")
        raise typer.Exit(2)
    if not target_site:
        console.print("[red]No site selected. Pair Edge again or use --site-id.[/red]")
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
    """Run Edge heartbeats, hardware inventory sync, and remote configuration fetches."""
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
        console.print("[red]UI dependencies missing.[/red]")
        raise typer.Exit(2) from exc
    from .local_ui import build_app

    console.print(f"Opening local Edge interface at http://{host}:{port}")
    uvicorn.run(build_app(), host=host, port=port, log_level="warning")


@app.command("logout")
def logout() -> None:
    """Remove the locally stored TerraSatch Edge device credential."""
    clear_api_key()
    console.print("[green]Local TerraSatch Edge credential removed.[/green]")


@app.command("paths")
def show_paths() -> None:
    """Show local configuration/state file locations."""
    paths = get_paths()
    console.print(f"Config: {paths.config_file}")
    console.print(f"Credentials: {paths.credentials_file}")
    console.print(f"Snapshot: {paths.snapshot_file}")
    console.print(f"Remote config: {paths.remote_config_file}")
    console.print(f"Logs: {paths.log_dir}")


if __name__ == "__main__":
    app()
