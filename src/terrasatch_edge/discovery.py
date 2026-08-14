from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import psutil
from .adapters import classify_device
from .config import get_paths
from .models import DeviceKind, HardwareDevice, SystemSnapshot


def _run(command: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _system_device() -> HardwareDevice:
    return HardwareDevice(
        kind=DeviceKind.SYSTEM,
        name=platform.node() or socket.gethostname(),
        identifier=platform.platform(),
        vendor=platform.system(),
        product=platform.machine(),
        capabilities=["edge_runtime"],
        metadata={"processor": platform.processor()},
    )


def _serial_devices() -> list[HardwareDevice]:
    try:
        from serial.tools import list_ports  # type: ignore[import-not-found]
    except ImportError:
        return []

    devices: list[HardwareDevice] = []
    for port in list_ports.comports():
        vendor_id = f"{port.vid:04x}" if port.vid is not None else None
        product_id = f"{port.pid:04x}" if port.pid is not None else None
        device = HardwareDevice(
            kind=DeviceKind.SERIAL,
            name=port.description or port.device,
            identifier=port.hwid or port.device,
            vendor=port.manufacturer,
            product=port.product,
            vendor_id=vendor_id,
            product_id=product_id,
            path=port.device,
            capabilities=["serial"],
            metadata={
                "serial_number": port.serial_number,
                "location": port.location,
                "interface": port.interface,
            },
        )
        devices.append(classify_device(device))
    return devices


def _pyusb_devices() -> list[HardwareDevice]:
    try:
        import usb.core  # type: ignore[import-not-found]
        import usb.util  # type: ignore[import-not-found]
    except ImportError:
        return []

    devices: list[HardwareDevice] = []
    try:
        found = usb.core.find(find_all=True)
    except Exception:
        return []

    for raw in found or []:
        vendor_id = f"{int(raw.idVendor):04x}"
        product_id = f"{int(raw.idProduct):04x}"
        manufacturer = None
        product = None
        serial_number = None
        try:
            manufacturer = usb.util.get_string(raw, raw.iManufacturer) if raw.iManufacturer else None
            product = usb.util.get_string(raw, raw.iProduct) if raw.iProduct else None
            serial_number = usb.util.get_string(raw, raw.iSerialNumber) if raw.iSerialNumber else None
        except Exception:
            pass

        name = product or f"USB {vendor_id}:{product_id}"
        device = HardwareDevice(
            kind=DeviceKind.USB,
            name=name,
            identifier=f"usb:{vendor_id}:{product_id}:{getattr(raw, 'bus', '?')}:{getattr(raw, 'address', '?')}",
            vendor=manufacturer,
            product=product,
            vendor_id=vendor_id,
            product_id=product_id,
            capabilities=["usb"],
            metadata={"serial_number": serial_number},
        )
        devices.append(classify_device(device))
    return devices


def _linux_lsusb_devices() -> list[HardwareDevice]:
    if shutil.which("lsusb") is None:
        return []
    result = _run(["lsusb"])
    if result is None or result.returncode != 0:
        return []

    devices: list[HardwareDevice] = []
    for line in result.stdout.splitlines():
        # Typical: Bus 001 Device 004: ID 0bda:2838 Realtek Semiconductor Corp. RTL2838 DVB-T
        if " ID " not in line:
            continue
        left, right = line.split(" ID ", 1)
        parts = right.split(maxsplit=1)
        ids = parts[0]
        name = parts[1] if len(parts) > 1 else f"USB {ids}"
        vendor_id, _, product_id = ids.partition(":")
        device = HardwareDevice(
            kind=DeviceKind.USB,
            name=name,
            identifier=f"lsusb:{ids}:{left.strip()}",
            vendor_id=vendor_id or None,
            product_id=product_id or None,
            capabilities=["usb"],
            metadata={"source": "lsusb"},
        )
        devices.append(classify_device(device))
    return devices


def _windows_pnp_devices() -> list[HardwareDevice]:
    if os.name != "nt" or shutil.which("powershell") is None:
        return []
    script = (
        "Get-PnpDevice -PresentOnly | Select-Object Class,FriendlyName,InstanceId,Status | "
        "ConvertTo-Json -Depth 3 -Compress"
    )
    result = _run(["powershell", "-NoProfile", "-Command", script], timeout=8.0)
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload: Any = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    devices: list[HardwareDevice] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("FriendlyName") or row.get("InstanceId") or "PnP device")
        identifier = str(row.get("InstanceId") or name)
        kind = DeviceKind.USB if "USB" in identifier.upper() else DeviceKind.UNKNOWN
        device = HardwareDevice(
            kind=kind,
            name=name,
            identifier=identifier,
            status=str(row.get("Status") or "detected").lower(),
            capabilities=["pnp"],
            metadata={"class": row.get("Class"), "source": "windows-pnp"},
        )
        classified = classify_device(device)
        if classified.kind != DeviceKind.UNKNOWN or kind == DeviceKind.USB:
            devices.append(classified)
    return devices


def _network_devices() -> list[HardwareDevice]:
    devices: list[HardwareDevice] = []
    stats = psutil.net_if_stats()
    addresses = psutil.net_if_addrs()
    for name, iface_stats in stats.items():
        addr_values: list[str] = []
        for address in addresses.get(name, []):
            value = getattr(address, "address", None)
            if value:
                addr_values.append(value)
        devices.append(
            HardwareDevice(
                kind=DeviceKind.NETWORK,
                name=name,
                identifier=f"net:{name}",
                status="up" if iface_stats.isup else "down",
                capabilities=["network"],
                metadata={
                    "speed_mbps": iface_stats.speed,
                    "mtu": iface_stats.mtu,
                    "addresses": addr_values,
                },
            )
        )
    return devices


def _tool_detected_sdrs() -> list[HardwareDevice]:
    devices: list[HardwareDevice] = []
    probes = [
        ("rtl_test", ["rtl_test", "-t"], "RTL-SDR", "rtl-sdr"),
        ("hackrf_info", ["hackrf_info"], "HackRF", "hackrf"),
        ("SoapySDRUtil", ["SoapySDRUtil", "--find"], "SoapySDR", "soapysdr"),
    ]
    for executable, command, name, identifier in probes:
        if shutil.which(executable) is None:
            continue
        result = _run(command, timeout=5.0)
        if result is None:
            continue
        combined = (result.stdout + "\n" + result.stderr).strip()
        lower = combined.lower()
        negative = any(
            marker in lower
            for marker in ("no supported devices found", "no device found", "no devices found")
        )
        if combined and not negative:
            devices.append(
                classify_device(
                    HardwareDevice(
                        kind=DeviceKind.SDR,
                        name=name,
                        identifier=f"probe:{identifier}",
                        capabilities=["radio_rx", "iq_stream"],
                        metadata={"source": executable, "probe_output": combined[:1500]},
                    )
                )
            )
    return devices


def _dedupe(devices: list[HardwareDevice]) -> list[HardwareDevice]:
    by_key: dict[tuple[str, str | None, str | None, str | None], HardwareDevice] = {}
    for device in devices:
        key = (
            device.identifier.lower(),
            device.vendor_id.lower() if device.vendor_id else None,
            device.product_id.lower() if device.product_id else None,
            device.path.lower() if device.path else None,
        )
        if key not in by_key:
            by_key[key] = device
    return list(by_key.values())


def scan_hardware(include_network: bool = True) -> SystemSnapshot:
    memory = psutil.virtual_memory()
    root = Path.home().anchor or os.sep
    disk = psutil.disk_usage(root)

    devices: list[HardwareDevice] = [_system_device()]
    devices.extend(_serial_devices())
    devices.extend(_pyusb_devices())
    if platform.system() == "Linux":
        devices.extend(_linux_lsusb_devices())
    if os.name == "nt":
        devices.extend(_windows_pnp_devices())
    devices.extend(_tool_detected_sdrs())
    if include_network:
        devices.extend(_network_devices())

    snapshot = SystemSnapshot(
        hostname=platform.node() or socket.gethostname(),
        platform=platform.system(),
        platform_release=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        cpu_count_logical=psutil.cpu_count(logical=True),
        memory_total_bytes=memory.total,
        memory_available_bytes=memory.available,
        disk_total_bytes=disk.total,
        disk_free_bytes=disk.free,
        devices=_dedupe(devices),
    )
    return snapshot


def save_snapshot(snapshot: SystemSnapshot) -> Path:
    path = get_paths().snapshot_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path
