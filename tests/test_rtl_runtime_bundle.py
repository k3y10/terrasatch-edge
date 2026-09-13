import runpy
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify-rtlsdr-runtime.py"


@pytest.mark.parametrize("code,output,valid", [(0, b"help", True), (1, b"help", True),
                                               (3221225781, b"", False), (-1073741515, b"", False),
                                               (0, b"", False)])
def test_native_runtime_rejects_loader_failure_and_ambient_path(tmp_path, monkeypatch, code, output, valid):
    for name in ("rtl_sdr.exe", "rtl_fm.exe", "rtl_test.exe"):
        (tmp_path / name).touch()
    monkeypatch.setenv("PATH", "developer-msys2-must-not-mask-missing-dll")
    def run(command, **kwargs):
        assert command[1] == "-h"
        assert "developer-msys2" not in kwargs["env"]["PATH"]
        return subprocess.CompletedProcess(command, code, stdout=output, stderr=b"")
    monkeypatch.setattr(subprocess, "run", run)
    verify = runpy.run_path(str(SCRIPT))["verify"]
    if valid:
        verify(tmp_path)
    else:
        with pytest.raises(RuntimeError, match="DLL dependencies"):
            verify(tmp_path)


def test_staging_inspects_every_utility_and_build_checks_actual_launch():
    root = SCRIPT.parents[1]
    staging = (root / "scripts/stage-rtlsdr-windows.ps1").read_text()
    build = (root / "scripts/build-windows.ps1").read_text()
    assert 'foreach ($Utility in $Utilities)' in staging
    assert 'ldd /ucrt64/bin/$Utility' in staging
    assert 'scripts\\verify-rtlsdr-runtime.py' in build
