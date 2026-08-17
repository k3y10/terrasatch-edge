from __future__ import annotations

from dataclasses import dataclass

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import load_api_key, load_config
from .discovery import scan_hardware
from .models import DeviceKind
from .tooling import find_executable, probe_rtl_sdr


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str
    recommendation: str | None = None


def run_doctor() -> list[DoctorCheck]:
    config = load_config()
    api_key = load_api_key()
    snapshot = scan_hardware(include_network=True)
    checks: list[DoctorCheck] = []

    checks.append(
        DoctorCheck(
            name="Configuration",
            ok=bool(config.api_url),
            detail=f"API: {config.api_url}",
        )
    )
    checks.append(
        DoctorCheck(
            name="Credentials",
            ok=bool(api_key),
            detail="Edge device credential present" if api_key else "No Edge device credential configured",
            recommendation="Run `terrasatch-edge setup` or set TERRASATCH_EDGE_API_KEY."
            if not api_key
            else None,
        )
    )

    client = TerraSatchApiClient(config.api_url, api_key)
    try:
        client.health()
        checks.append(DoctorCheck(name="API reachability", ok=True, detail="API health endpoint reachable"))
    except TerraSatchApiError as exc:
        checks.append(
            DoctorCheck(
                name="API reachability",
                ok=False,
                detail=str(exc),
                recommendation="Check internet access, DNS, TLS, and the configured API URL.",
            )
        )

    if api_key:
        try:
            client.identity()
            checks.append(DoctorCheck(name="Authentication", ok=True, detail="Edge credential accepted"))
        except TerraSatchApiError as exc:
            checks.append(
                DoctorCheck(
                    name="Authentication",
                    ok=False,
                    detail=str(exc),
                    recommendation="Pair this Edge node again to issue a valid device credential.",
                )
            )

    sdrs = [d for d in snapshot.devices if d.kind == DeviceKind.SDR]
    gps = [d for d in snapshot.devices if d.kind == DeviceKind.GPS]
    audio = [d for d in snapshot.devices if d.kind == DeviceKind.AUDIO]
    serial = [d for d in snapshot.devices if d.kind == DeviceKind.SERIAL]
    rtl_sdrs = [
        device
        for device in sdrs
        if {"rtl-sdr", "nooelec", "radio:rx", "radio:receive"}.intersection(device.capabilities)
    ]

    checks.append(
        DoctorCheck(
            name="SDR hardware",
            ok=bool(sdrs),
            detail=f"{len(sdrs)} SDR device(s) recognized" if sdrs else "No recognized SDR detected",
            recommendation="Connect a supported RTL-SDR/Nooelec or HackRF and install its driver."
            if not sdrs
            else None,
        )
    )

    rtl_runtime = find_executable("rtl_sdr")
    if rtl_sdrs:
        checks.append(
            DoctorCheck(
                name="RTL-SDR runtime",
                ok=rtl_runtime is not None,
                detail=str(rtl_runtime) if rtl_runtime else "rtl_sdr executable not found",
                recommendation=(
                    "Install an Edge build with the TerraSatch RTL-SDR tool bundle, or set "
                    "TERRASATCH_EDGE_TOOLS to a trusted rtl-sdr folder."
                    if rtl_runtime is None
                    else None
                ),
            )
        )
        if rtl_runtime is not None:
            probe = probe_rtl_sdr()
            checks.append(
                DoctorCheck(
                    name="SDR receive probe",
                    ok=probe.ok,
                    detail=probe.detail,
                    recommendation=(
                        "Verify the Nooelec uses the WinUSB driver on Interface 0 and that no other SDR application "
                        "currently owns the device."
                        if not probe.ok
                        else None
                    ),
                )
            )

    gps_detail = (
        f"{len(gps)} GPS/GNSS device(s) recognized" if gps else "No recognized GPS detected"
    )
    checks.append(
        DoctorCheck(
            name="GPS hardware",
            ok=bool(gps),
            detail=gps_detail,
            recommendation="GPS is optional; connect a USB/NMEA GPS if mapping requires local position."
            if not gps
            else None,
        )
    )

    checks.append(
        DoctorCheck(
            name="Audio interface",
            ok=bool(audio),
            detail=f"{len(audio)} recognized audio device(s)" if audio else "No recognized radio/audio interface detected",
            recommendation=(
                "This is expected for RTL-SDR-only receive testing. Connect a supported USB audio/radio interface "
                "when testing direct radio audio."
                if not audio
                else None
            ),
        )
    )
    checks.append(
        DoctorCheck(
            name="Serial interfaces",
            ok=True,
            detail=f"{len(serial)} serial device(s) detected" if serial else "No serial devices detected (optional)",
        )
    )

    other_tools: list[str] = []
    for name in ("hackrf_info", "SoapySDRUtil"):
        executable = find_executable(name)
        if executable:
            other_tools.append(f"{name}: {executable}")
    if other_tools:
        checks.append(
            DoctorCheck(
                name="Additional SDR tools",
                ok=True,
                detail="; ".join(other_tools),
            )
        )

    return checks
