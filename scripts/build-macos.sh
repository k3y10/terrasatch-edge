#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -e '.[serial,usb,ui,build,dev]'
.build-venv/bin/python -m pytest
rm -rf build dist release/macos-root
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name TerraSatchEdge --collect-all uvicorn --collect-all fastapi packaging/entrypoints/edge_cli.py

mkdir -p release/macos-root/usr/local/lib/terrasatch-edge
cp -R dist/TerraSatchEdge/. release/macos-root/usr/local/lib/terrasatch-edge/
mkdir -p release/macos-root/usr/local/bin
ln -sf ../lib/terrasatch-edge/TerraSatchEdge release/macos-root/usr/local/bin/terrasatch-edge

pkgbuild \
  --root release/macos-root \
  --identifier com.terrasatch.edge \
  --version 0.2.0 \
  --install-location / \
  release/TerraSatch-Edge-0.2.0.pkg

echo "Built release/TerraSatch-Edge-0.2.0.pkg"
echo "Production distribution still requires Apple Developer signing/notarization."
