from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


APP_NAME = "TerraSatchEdge"


def _default_config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) / "terrasatch-edge" if xdg else Path.home() / ".config" / "terrasatch-edge"


def _default_state_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / APP_NAME
    xdg = os.environ.get("XDG_STATE_HOME")
    return Path(xdg) / "terrasatch-edge" if xdg else Path.home() / ".local" / "state" / "terrasatch-edge"


class EdgeConfig(BaseModel):
    api_url: str = "https://api.terrasatch.com"
    site_id: str | None = None
    site_name: str | None = None
    node_name: str | None = None
    scan_interval_seconds: int = Field(default=30, ge=5, le=3600)
    source: str = "terrasatch-edge"


@dataclass(frozen=True)
class Paths:
    config_dir: Path
    state_dir: Path
    config_file: Path
    credentials_file: Path
    snapshot_file: Path


def get_paths() -> Paths:
    config_dir = Path(os.environ.get("TERRASATCH_EDGE_CONFIG_DIR", _default_config_dir()))
    state_dir = Path(os.environ.get("TERRASATCH_EDGE_STATE_DIR", _default_state_dir()))
    return Paths(
        config_dir=config_dir,
        state_dir=state_dir,
        config_file=config_dir / "config.json",
        credentials_file=config_dir / "credentials.json",
        snapshot_file=state_dir / "hardware-snapshot.json",
    )


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _tighten_permissions(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


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
        data["scan_interval_seconds"] = int(env_interval)

    try:
        return EdgeConfig.model_validate(data)
    except ValidationError:
        return EdgeConfig()


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
