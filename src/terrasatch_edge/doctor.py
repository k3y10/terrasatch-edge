from __future__ import annotations

import shutil
from dataclasses import dataclass

from .api import TerraSatchApiClient, TerraSatchApiError
from .config import load_api_key, load_config
from .discovery import scan_hardware
from .models import DeviceKind


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
            detail="Service API key present" if api_key else "No service API key configured",
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
            checks.append(DoctorCheck(name="Authentication", ok=True, detail="API key accepted"))
        except TerraSatchApiError as exc:
            checks.append(
                DoctorCheck(
                    name="Authentication",
                    ok=False,
                    detail=str(exc),
                    recommendation="Issue a valid TerraSatch service key and rerun setup.",
                )
            )

    sdrs = [d for d in snapshot.devices if d.kind == DeviceKind.SDR]
    gps = [d for d in snapshot.devices if d.kind == DeviceKind.GPS]
    audio = [d for d in snapshot.devices if d.kind == DeviceKind.AUDIO]
    serial = [d for d in snapshot.devices if d.kind == DeviceKind.SERIAL]

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
    checks.append(
        DoctorCheck(
            name="GPS hardware",
            ok=bool(gps),
            detail=f"{len(gps)} GPS/GNSS device(s) recognized" if gps else "No recognized GPS detected",
            recommendation="GPS is optional; connect a USB/NMEA GPS if mapping requires local position."
            if not gps
            else None,
        )
    )
    checks.append(
        DoctorCheck(
            name="Audio interface",
            ok=bool(audio) or bool(serial),
            detail=(
                f"{len(audio)} recognized audio device(s), {len(serial)} serial device(s)"
                if audio or serial
                else "No radio/audio interface recognized by current rules"
            ),
            recommendation="Connect the radio audio interface; generic audio enumeration is expanded in the next adapter phase."
            if not audio and not serial
            else None,
        )
    )

    tool_names = [name for name in ("rtl_test", "hackrf_info", "SoapySDRUtil") if shutil.which(name)]
    checks.append(
        DoctorCheck(
            name="SDR tools",
            ok=bool(tool_names) or not sdrs,
            detail=", ".join(tool_names) if tool_names else "No SDR command-line probe tools found",
            recommendation="Install rtl-sdr, HackRF tools, or SoapySDR for deeper radio diagnostics."
            if sdrs and not tool_names
            else None,
        )
    )

    return checks
