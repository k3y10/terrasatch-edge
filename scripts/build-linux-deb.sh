#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -e '.[serial,usb,ui,build,dev]'
.build-venv/bin/python -m pytest
rm -rf build dist release/linux-root
.build-venv/bin/python -m PyInstaller --noconfirm --clean --onedir --name terrasatch-edge --collect-all uvicorn --collect-all fastapi packaging/entrypoints/edge_cli.py

ARCH="$(dpkg --print-architecture)"
PKGROOT="release/linux-root"
mkdir -p "$PKGROOT/DEBIAN" "$PKGROOT/opt/terrasatch-edge" "$PKGROOT/usr/local/bin" "$PKGROOT/etc/systemd/system"
cp -R dist/terrasatch-edge/. "$PKGROOT/opt/terrasatch-edge/"
ln -sf /opt/terrasatch-edge/terrasatch-edge "$PKGROOT/usr/local/bin/terrasatch-edge"
cat > "$PKGROOT/etc/systemd/system/terrasatch-edge.service" <<'UNIT'
[Unit]
Description=TerraSatch Edge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/opt/terrasatch-edge/terrasatch-edge run
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
UNIT
cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: terrasatch-edge
Version: 0.2.0
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: TerraSatch
Description: TerraSatch field-device Edge runtime
EOF
cat > "$PKGROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
systemctl daemon-reload || true
systemctl enable terrasatch-edge.service || true
EOF
cat > "$PKGROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
systemctl stop terrasatch-edge.service || true
systemctl disable terrasatch-edge.service || true
EOF
chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/prerm"
mkdir -p release
dpkg-deb --build "$PKGROOT" "release/terrasatch-edge_0.2.0_${ARCH}.deb"
echo "Built release/terrasatch-edge_0.2.0_${ARCH}.deb"
