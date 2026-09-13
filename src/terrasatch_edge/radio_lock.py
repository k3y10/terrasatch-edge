"""OS-held receiver leases, released on exit/crash; never delete lock files."""

from __future__ import annotations

import os
from pathlib import Path

from .config import get_paths


class ReceiverLock:
    def __init__(self, device_index: int = 0, *, root: Path | None = None, name: str | None = None):
        self.path = (root or get_paths().state_dir / "radio-locks") / (name or f"rtl-{device_index}.lock")
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError("Receiver is already in use by another Edge radio operation") from exc
        return self

    def __exit__(self, *_args):
        if self.file is not None:
            self.file.close()
            self.file = None
