from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SdrProbeResult:
    ok: bool
    executable: Path | None
    detail: str
    output: str = ""


def _tool_dirs() -> list[Path]:
    directories: list[Path] = []

    configured = os.environ.get("TERRASATCH_EDGE_TOOLS")
    if configured:
        directories.append(Path(configured).expanduser())

    executable_dir = Path(sys.executable).resolve().parent
    directories.extend(
        [
            executable_dir / "tools" / "rtl-sdr",
            executable_dir / "tools",
            executable_dir.parent / "tools" / "rtl-sdr",
            executable_dir.parent / "tools",
        ]
    )

    program_data = os.environ.get("ProgramData")
    if program_data:
        directories.extend(
            [
                Path(program_data) / "TerraSatch" / "Edge" / "tools" / "rtl-sdr",
                Path(program_data) / "TerraSatch" / "Edge" / "tools",
            ]
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for directory in directories:
        key = str(directory).lower()
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique


def find_executable(name: str) -> Path | None:
    """Resolve a helper from an explicit/bundled TerraSatch location, then PATH.

    ``TERRASATCH_EDGE_TOOLS`` is an operator override and must win over a
    system-installed binary. Bundled TerraSatch helper directories are checked
    next so packaged runtimes remain deterministic. System ``PATH`` is the
    fallback for native Linux/macOS installations such as distro/Homebrew
    ``rtl-sdr`` packages.
    """

    candidates = [name]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        candidates.insert(0, f"{name}.exe")

    for directory in _tool_dirs():
        for candidate in candidates:
            path = directory / candidate
            if path.is_file():
                return path

    system_match = shutil.which(name)
    if system_match:
        return Path(system_match)
    return None


def probe_rtl_sdr(
    *,
    frequency_hz: int = 100_000_000,
    sample_rate: int = 240_000,
    sample_count: int = 200_000,
    timeout_seconds: float = 12.0,
) -> SdrProbeResult:
    """Open an RTL-SDR receiver and read a small, finite IQ sample.

    The default sample count is intentionally not block-aligned. Upstream
    ``rtl_sdr`` only cancels its asynchronous reader when the remaining byte
    count is *less than* the callback block length. A request that lands on an
    exact block boundary can therefore continue reading indefinitely after the
    requested data has already been written. Keeping this probe non-aligned
    makes the diagnostic reliably finite on Windows and other platforms.
    """
    executable = find_executable("rtl_sdr")
    if executable is None:
        return SdrProbeResult(
            ok=False,
            executable=None,
            detail="RTL-SDR runtime not found",
        )

    with tempfile.TemporaryDirectory(prefix="terrasatch-sdr-") as temp_dir:
        output_path = Path(temp_dir) / "probe.iq"
        command = [
            str(executable),
            "-f",
            str(frequency_hz),
            "-s",
            str(sample_rate),
            "-n",
            str(sample_count),
            str(output_path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(
                part for part in (exc.stdout, exc.stderr) if isinstance(part, str)
            ).strip()
            suffix = f" · {output[-500:]}" if output else ""
            return SdrProbeResult(
                ok=False,
                executable=executable,
                detail=f"RTL-SDR receive probe timed out after {timeout_seconds:g}s{suffix}",
                output=output[-2000:],
            )
        except OSError as exc:
            return SdrProbeResult(
                ok=False,
                executable=executable,
                detail=f"Could not start RTL-SDR runtime: {exc}",
            )

        combined = (result.stdout + "\n" + result.stderr).strip()
        bytes_read = output_path.stat().st_size if output_path.exists() else 0
        if result.returncode == 0 and bytes_read > 0:
            return SdrProbeResult(
                ok=True,
                executable=executable,
                detail=(
                    f"Read {bytes_read:,} IQ bytes at {frequency_hz / 1_000_000:.3f} MHz "
                    f"with {executable.name}"
                ),
                output=combined[-2000:],
            )

        lower = combined.lower()
        if "no supported devices found" in lower or "no devices found" in lower:
            detail = "RTL-SDR runtime is installed but no compatible receiver could be opened"
        elif "usb_claim_interface" in lower or "access denied" in lower:
            detail = "RTL-SDR runtime found the receiver but could not claim its USB interface"
        elif "failed to open rtlsdr device" in lower:
            detail = "RTL-SDR found the receiver but could not open it; close other SDR apps and verify device permissions/driver access"
        else:
            detail = f"RTL-SDR receive probe failed with exit code {result.returncode}"

        if combined:
            detail = f"{detail} · {combined[-500:]}"

        return SdrProbeResult(
            ok=False,
            executable=executable,
            detail=detail,
            output=combined[-2000:],
        )
