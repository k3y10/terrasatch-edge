"""Reject an incomplete native RTL bundle without opening a USB receiver."""

import os
from pathlib import Path
import subprocess
import sys


def verify(root: Path) -> None:
    environment = dict(os.environ)
    # Do not let a developer's MSYS2 PATH hide missing redistributed DLLs.
    windows = Path(environment.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join(map(str, (root, windows / "System32", windows)))
    for name in ("rtl_sdr.exe", "rtl_fm.exe", "rtl_test.exe"):
        executable = root / name
        if not executable.is_file():
            raise RuntimeError(f"Incomplete RTL runtime: missing {name}")
        try:
            result = subprocess.run([str(executable), "-h"], env=environment,
                                    capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"RTL runtime cannot launch {name}; verify its DLL dependencies") from exc
        # These utilities use either success or usage-error for their help option.
        if result.returncode not in (0, 1) or not (result.stdout or result.stderr):
            raise RuntimeError(f"RTL runtime cannot launch {name} (exit {result.returncode}); "
                               "verify its DLL dependencies, including MSYS2 libwinpthread-1.dll")


if __name__ == "__main__":
    verify(Path(sys.argv[1]).resolve())
    print("RTL-SDR, FM and test utilities launch successfully without developer PATH dependencies")
