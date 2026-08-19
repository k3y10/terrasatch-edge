"""Expose TerraSatch Edge's private PyInstaller hook directory."""

from pathlib import Path


def get_hook_dirs() -> list[str]:
    return [str(Path(__file__).resolve().with_name("_pyinstaller_hooks"))]
