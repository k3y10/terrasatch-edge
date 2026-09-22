from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_console_scripts_use_shared_version_aware_entrypoint() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = payload["project"]["scripts"]

    assert scripts["terrasatch-edge"] == "terrasatch_edge.entrypoint:main"
    assert scripts["tsedge"] == "terrasatch_edge.entrypoint:main"


def test_windows_installer_version_matches_project_version() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = payload["project"]["version"]
    installer = (ROOT / "packaging" / "windows" / "TerraSatchEdge.iss").read_text(
        encoding="utf-8"
    )

    assert f'#define MyAppVersion "{version}"' in installer


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


def test_windows_release_build_bundles_brand_assets_and_requires_trusted_signing() -> None:
    build_script = (ROOT / "scripts" / "build-windows.ps1").read_text(encoding="utf-8")
    installer = (ROOT / "packaging" / "windows" / "TerraSatchEdge.iss").read_text(
        encoding="utf-8"
    )
    brand_dir = ROOT / "src" / "terrasatch_edge" / "assets"

    assert (brand_dir / "terrasatch-logo.png").stat().st_size > 100_000
    assert (brand_dir / "satchy-approved-current.webp").stat().st_size > 5_000
    assert not (brand_dir / "terrasatch-logo.webp").exists()
    assert not (brand_dir / "terrasatch-black-logo.png").exists()
    assert '"--collect-data", "terrasatch_edge"' in build_script
    assert "TERRASATCH_CODESIGN_CERT_THUMBPRINT" in build_script
    assert "[switch]$AllowUnsigned" in build_script
    assert '"/fd", "SHA256"' in build_script
    assert '"/td", "SHA256"' in build_script
    assert "Invoke-AuthenticodeSign -Path $WinSW" in build_script
    assert "Assert-AuthenticodeSignature -Path $Installer" in build_script
    assert "#ifdef SignedRelease" in installer
    assert "SignTool=TerraSatch" in installer
    assert "SignedUninstaller=yes" in installer


def test_edge_env_example_points_at_production_https() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "TERRASATCH_EDGE_API_URL=https://api.terrasatch.com" in text


def test_store_msix_uses_satchy_branding_and_startup_tasks() -> None:
    manifest = (
        ROOT / "packaging" / "windows" / "msix" / "AppxManifest.template.xml"
    ).read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build-windows-msix.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Category="windows.startupTask"' in manifest
    assert 'TaskId="TerraSatchEdgeAgent"' in manifest
    assert 'TaskId="TerraSatchRadio"' in manifest
    assert 'Enabled="true"' in manifest
    assert 'Enabled="false"' in manifest
    assert "packagedServices" not in manifest
    assert "localSystemServices" not in manifest
    assert "terrasatch-logo.png" in build_script
    assert '"#111317"' in build_script
    assert '"#f2960d"' in build_script


def test_operator_console_uses_current_satchy_gateway_theme_and_flow() -> None:
    operator_page = (ROOT / "src" / "terrasatch_edge" / "operator_page.py").read_text(
        encoding="utf-8"
    )

    assert "--bg:#111317" in operator_page
    assert "--surface:#1b1d22" in operator_page
    assert "--surface2:#292c32" in operator_page
    assert "--surface3:#0d0e12" in operator_page
    assert "--line:#2e3138" in operator_page
    assert "--soft:#25272d" in operator_page
    assert "--text:#e9e7e2" in operator_page
    assert "--muted:#838995" in operator_page
    assert "--orange:#f2960d" in operator_page
    assert "--positive:#42d17b" in operator_page
    assert "TerraSatch field runtime" in operator_page
    assert "Pair your workspace" in operator_page
    assert "Use what the field already uses" in operator_page
    assert "Phone / TerraSatch Mobile" in operator_page
    assert "Radio / SDR" in operator_page
    assert "Meshtastic / LoRa" in operator_page
    assert "Garmin / inReach" in operator_page
    assert "does not need to be plugged into this Edge computer" in operator_page
    assert "Direct to TerraSatch" in operator_page
    assert "Through this Edge" in operator_page
    assert "Adapter planned" in operator_page
    assert "Provider to TerraSatch" in operator_page
    assert "Edge when local" in operator_page
    assert "Signal path" in operator_page
    assert "Current result: architecture is reserved" in operator_page
    assert "Pair with phone or browser" in operator_page
    assert "qr_data_uri" in (ROOT / "src" / "terrasatch_edge" / "local_ui.py").read_text(encoding="utf-8")
    assert "Keep field observations in the same operational context." in operator_page
    assert "Arbitrary SMS/iMessage/third-party chat ingestion" in operator_page
    assert "binary media upload" in operator_page
    assert "Radio receive" in operator_page
    assert "This does not enable transmit." in operator_page
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "qrcode>=8,<9" in pyproject
    assert "/assets/terrasatch-logo.png" in operator_page
    assert "/assets/satchy-approved-current.webp" in operator_page
    assert "Satchy turns field signals into shared operational context while preserving where each piece of information came from." in operator_page
    assert "Consequential outputs remain traceable and human-reviewed." in operator_page
    assert "Scan local hardware" in operator_page
