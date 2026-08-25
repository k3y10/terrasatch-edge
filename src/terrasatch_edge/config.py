from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError


APP_NAME = "TerraSatchEdge"


def _default_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", Path.home() / "AppData" / "Local"))
        return base / "TerraSatch" / "Edge"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "terrasatch-edge" if xdg else Path.home() / ".config" / "terrasatch-edge"


def _default_state_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA", Path.home() / "AppData" / "Local"))
        return base / "TerraSatch" / "Edge" / "state"
    xdg = os.environ.get("XDG_STATE_HOME")
    return Path(xdg) / "terrasatch-edge" if xdg else Path.home() / ".local" / "state" / "terrasatch-edge"


class EdgeConfig(BaseModel):
    api_url: str = "https://api.terrasatch.com"
    device_id: str | None = None
    organization_id: str | None = None
    site_id: str | None = None
    site_name: str | None = None
    node_name: str | None = None
    scan_interval_seconds: int = Field(default=30, ge=5, le=3600)
    source: str = "terrasatch-edge"
    speech_model: str = "base.en"
    speech_device: str = "cpu"
    speech_compute_type: str = "int8"
    speech_language: str | None = "en"
    speech_vad_filter: bool = True
    speech_local_files_only: bool = False

    # Receive-only BCA/FRS pilot settings. These do not enable SDR transmission.
    radio_profile: str = "bca-frs-na"
    radio_channel: int | None = Field(default=None, ge=1, le=22)
    radio_output_sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    radio_demod_sample_rate: int = Field(default=24_000, ge=8_000, le=250_000)
    radio_squelch: int = Field(default=20, ge=1, le=100)
    radio_squelch_delay: int = Field(default=10, ge=1, le=10_000)
    radio_gain_db: float | None = Field(default=None, ge=0, le=60)
    radio_chunk_seconds: float = Field(default=0.20, gt=0, le=2)
    radio_silence_seconds: float = Field(default=0.90, gt=0, le=10)
    radio_min_transmission_seconds: float = Field(default=0.40, gt=0, le=10)
    radio_max_transmission_seconds: float = Field(default=30.0, ge=1, le=300)


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    state_dir: Path
    config_file: Path
    credentials_file: Path
    snapshot_file: Path
    remote_config_file: Path
    log_dir: Path


def get_paths() -> Paths:
    config_dir = Path(os.environ.get("TERRASATCH_EDGE_CONFIG_DIR", _default_config_dir()))
    state_dir = Path(os.environ.get("TERRASATCH_EDGE_STATE_DIR", _default_state_dir()))
    return Paths(
        config_dir=config_dir,
        state_dir=state_dir,
        config_file=config_dir / "config.json",
        credentials_file=config_dir / "credentials.json",
        snapshot_file=state_dir / "hardware-snapshot.json",
        remote_config_file=state_dir / "remote-config.json",
        log_dir=state_dir / "logs",
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _tighten_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)
        return
    username = os.environ.get("USERNAME")
    if not username:
        return
    try:
        subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{username}:(F)",
                "SYSTEM:(F)",
                "Administrators:(F)",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def load_config() -> EdgeConfig:
    paths = get_paths()
    env_api = os.environ.get("TERRASATCH_EDGE_API_URL")
    env_site = os.environ.get("TERRASATCH_EDGE_SITE_ID")
    env_interval = os.environ.get("TERRASATCH_EDGE_SCAN_INTERVAL_SECONDS")

    data: dict[str, object] = {}
    if paths.config_file.exists():
        try:
            data = json.loads(paths.config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}

    if env_api:
        data["api_url"] = env_api
    if env_site:
        data["site_id"] = env_site
    if env_interval:
        try:
            data["scan_interval_seconds"] = int(env_interval)
        except ValueError:
            pass

    string_overrides = {
        "speech_model": "TERRASATCH_EDGE_SPEECH_MODEL",
        "speech_device": "TERRASATCH_EDGE_SPEECH_DEVICE",
        "speech_compute_type": "TERRASATCH_EDGE_SPEECH_COMPUTE_TYPE",
        "speech_language": "TERRASATCH_EDGE_SPEECH_LANGUAGE",
        "radio_profile": "TERRASATCH_EDGE_RADIO_PROFILE",
    }
    for field_name, env_name in string_overrides.items():
        raw = os.environ.get(env_name)
        if raw:
            data[field_name] = raw.strip()

    for field_name, env_name in (
        ("speech_vad_filter", "TERRASATCH_EDGE_SPEECH_VAD_FILTER"),
        ("speech_local_files_only", "TERRASATCH_EDGE_SPEECH_LOCAL_FILES_ONLY"),
    ):
        value = _env_bool(env_name)
        if value is not None:
            data[field_name] = value

    int_overrides = {
        "radio_channel": "TERRASATCH_EDGE_RADIO_CHANNEL",
        "radio_output_sample_rate": "TERRASATCH_EDGE_RADIO_OUTPUT_SAMPLE_RATE",
        "radio_demod_sample_rate": "TERRASATCH_EDGE_RADIO_DEMOD_SAMPLE_RATE",
        "radio_squelch": "TERRASATCH_EDGE_RADIO_SQUELCH",
        "radio_squelch_delay": "TERRASATCH_EDGE_RADIO_SQUELCH_DELAY",
    }
    for field_name, env_name in int_overrides.items():
        value = _env_int(env_name)
        if value is not None:
            data[field_name] = value

    float_overrides = {
        "radio_gain_db": "TERRASATCH_EDGE_RADIO_GAIN_DB",
        "radio_chunk_seconds": "TERRASATCH_EDGE_RADIO_CHUNK_SECONDS",
        "radio_silence_seconds": "TERRASATCH_EDGE_RADIO_SILENCE_SECONDS",
        "radio_min_transmission_seconds": "TERRASATCH_EDGE_RADIO_MIN_SECONDS",
        "radio_max_transmission_seconds": "TERRASATCH_EDGE_RADIO_MAX_SECONDS",
    }
    for field_name, env_name in float_overrides.items():
        value = _env_float(env_name)
        if value is not None:
            data[field_name] = value

    try:
        return EdgeConfig.model_validate(data)
    except (ValidationError, ValueError):
        return EdgeConfig()


def update_registration_config(
    current: EdgeConfig,
    *,
    api_url: str,
    device_id: str | None,
    organization_id: str | None,
    site_id: str | None,
    site_name: str | None,
    node_name: str | None,
) -> EdgeConfig:
    """Update pairing identity without resetting speech/radio tuning."""

    data = current.model_dump()
    data.update(
        {
            "api_url": api_url,
            "device_id": device_id,
            "organization_id": organization_id,
            "site_id": site_id,
            "site_name": site_name,
            "node_name": node_name,
        }
    )
    return EdgeConfig.model_validate(data)


def save_config(config: EdgeConfig) -> Path:
    paths = get_paths()
    _ensure_parent(paths.config_file)
    paths.config_file.write_text(
        json.dumps(config.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _tighten_permissions(paths.config_file)
    return paths.config_file


def load_api_key() -> str | None:
    env_key = os.environ.get("TERRASATCH_EDGE_API_KEY")
    if env_key:
        return env_key.strip()

    path = get_paths().credentials_file
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    value = payload.get("api_key")
    return value.strip() if isinstance(value, str) and value.strip() else None


def save_api_key(api_key: str) -> Path:
    path = get_paths().credentials_file
    _ensure_parent(path)
    path.write_text(json.dumps({"api_key": api_key.strip()}, indent=2) + "\n", encoding="utf-8")
    _tighten_permissions(path)
    return path


def clear_api_key() -> None:
    path = get_paths().credentials_file
    if path.exists():
        path.unlink()


def save_remote_config(payload: dict[str, Any]) -> Path:
    path = get_paths().remote_config_file
    _ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _tighten_permissions(path)
    return path


def load_remote_config() -> dict[str, Any]:
    path = get_paths().remote_config_file
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
