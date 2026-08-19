from __future__ import annotations

import tomllib
from pathlib import Path

from terrasatch_edge.pyinstaller_hooks import get_hook_dirs


ROOT = Path(__file__).resolve().parents[1]


def test_native_build_extra_contains_local_speech_runtime() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional = payload["project"]["optional-dependencies"]
    assert "faster-whisper>=1.1,<2" in optional["speech"]
    assert "faster-whisper>=1.1,<2" in optional["build"]


def test_pyinstaller_discovers_terrasatch_speech_hook() -> None:
    payload = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entry_points = payload["project"]["entry-points"]["pyinstaller40"]
    assert entry_points["hook-dirs"] == "terrasatch_edge.pyinstaller_hooks:get_hook_dirs"

    hook_dir = Path(get_hook_dirs()[0])
    hook = hook_dir / "hook-terrasatch_edge.speech.py"
    assert hook.is_file()
    text = hook.read_text(encoding="utf-8")
    assert 'collect_all("faster_whisper")' in text
    assert 'collect_all("ctranslate2")' in text
