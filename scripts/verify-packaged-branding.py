"""Smoke-test the frozen console, including its bundled production artwork."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image


def main() -> None:
    executable = Path(sys.argv[1]).resolve(strict=True)
    canonical = Path(__file__).resolve().parents[1] / "src/terrasatch_edge/assets"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="terrasatch-package-brand-") as state:
        environment = dict(os.environ)
        environment.pop("TERRASATCH_EDGE_API_KEY", None)
        environment.update(
            TERRASATCH_EDGE_CONFIG_DIR=str(Path(state) / "config"),
            TERRASATCH_EDGE_STATE_DIR=str(Path(state) / "state"),
            TERRASATCH_EDGE_API_URL="http://127.0.0.1:1",
        )
        process = subprocess.Popen(
            [str(executable), "ui", "--host", "127.0.0.1", "--port", str(port)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for name, media_type in (
                ("terrasatch-logo.png", "image/png"),
            ):
                deadline = time.monotonic() + 30
                while True:
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/assets/{name}", timeout=3) as response:
                            data = response.read()
                            assert response.headers.get_content_type() == media_type, name
                        break
                    except URLError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.2)
                expected = (canonical / name).read_bytes()
                assert data == expected, f"Packaged artwork differs: {name}"
                with Image.open(io.BytesIO(data)) as artwork:
                    artwork.load()  # Headers/dimensions alone can pass for truncated images.
                print(f"Verified packaged {name}: {hashlib.sha256(data).hexdigest()}")
            with urlopen(f"http://127.0.0.1:{port}/", timeout=10) as response:
                page = response.read().decode()
            assert "Field Intelligence" in page, "Production wording missing"
            assert '/assets/terrasatch-logo.png' in page, "Canonical logo missing"
            assert '/assets/satchy-approved-current.webp' not in page, "Truncated legacy artwork rendered"
            print("Packaged Edge console renders with production branding.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
