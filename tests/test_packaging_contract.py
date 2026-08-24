from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_console_scripts_use_shared_version_aware_entrypoint() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = payload["project"]["scripts"]

    assert scripts["terrasatch-edge"] == "terrasatch_edge.entrypoint:main"
    assert scripts["tsedge"] == "terrasatch_edge.entrypoint:main"


def test_windows_setup_uses_production_api_environment_contract() -> None:
    script = (ROOT / "packaging" / "windows" / "TerraSatchEdgeSetup.ps1").read_text(
        encoding="utf-8"
    )

    assert '$ProductionApiUrl = "https://api.terrasatch.com"' in script
    assert "$env:TERRASATCH_EDGE_API_URL" in script
    assert "setup --api-url $SelectedApiUrl" in script
    assert "$EdgeExe --version" in script


def test_windows_installer_launches_operator_console_by_default() -> None:
    installer = (ROOT / "packaging" / "windows" / "TerraSatchEdge.iss").read_text(
        encoding="utf-8"
    )
    launcher = (ROOT / "packaging" / "windows" / "TerraSatchEdgeConsole.ps1").read_text(
        encoding="utf-8"
    )

    assert "TerraSatch Edge Setup and Console" in installer
    assert "-Command console" in installer
    assert "TerraSatch Edge Advanced Terminal Setup" in installer
    assert "runasoriginaluser" in installer
    assert '[ValidateSet("console", "status", "doctor", "scan")]' in launcher
    assert '[string]$Command = "console"' in launcher
    assert 'TERRASATCH_EDGE_WINDOWS_CONSOLE = "1"' in launcher


def test_windows_service_forces_utf8_for_redirected_logs() -> None:
    service_xml = (
        ROOT / "packaging" / "windows" / "TerraSatchEdgeService.xml"
    ).read_text(encoding="utf-8")

    assert '<env name="PYTHONUTF8" value="1"/>' in service_xml
    assert '<env name="PYTHONIOENCODING" value="utf-8"/>' in service_xml


def test_edge_env_example_points_at_production_https() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "TERRASATCH_EDGE_API_URL=https://api.terrasatch.com" in text
