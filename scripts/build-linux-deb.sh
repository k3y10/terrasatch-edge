#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD_VENV="$ROOT/.build-venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required to build TerraSatch Edge." >&2
  exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb is required to build the Debian package." >&2
  exit 1
fi

if [[ ! -d "$BUILD_VENV" ]]; then
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi
PYTHON="$BUILD_VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e '.[serial,usb,ui,build,dev]'

VERSION="$($PYTHON -c 'import terrasatch_edge; print(terrasatch_edge.__version__)')"
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Unsupported public pilot architecture: $ARCH (expected amd64 or arm64)." >&2
    exit 1
    ;;
esac

"$PYTHON" -m pytest
rm -rf build dist release/linux-root
"$PYTHON" -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name terrasatch-edge \
  --collect-all uvicorn \
  --collect-all fastapi \
  packaging/entrypoints/edge_cli.py

PKGROOT="$ROOT/release/linux-root"
INSTALL_ROOT="$PKGROOT/opt/terrasatch-edge"
CONFIG_DIR="$PKGROOT/etc/terrasatch-edge"
STATE_DIR="$PKGROOT/var/lib/terrasatch-edge"
LOG_DIR="$STATE_DIR/logs"
UNIT_DIR="$PKGROOT/lib/systemd/system"
WRAPPER="$PKGROOT/usr/local/bin/terrasatch-edge"

mkdir -p \
  "$PKGROOT/DEBIAN" \
  "$INSTALL_ROOT" \
  "$CONFIG_DIR" \
  "$LOG_DIR" \
  "$UNIT_DIR" \
  "$(dirname "$WRAPPER")"
cp -R dist/terrasatch-edge/. "$INSTALL_ROOT/"

cat > "$WRAPPER" <<'EOF'
#!/bin/sh
export TERRASATCH_EDGE_CONFIG_DIR="/etc/terrasatch-edge"
export TERRASATCH_EDGE_STATE_DIR="/var/lib/terrasatch-edge"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin${PATH:+:$PATH}"
exec /opt/terrasatch-edge/terrasatch-edge "$@"
EOF
chmod 755 "$WRAPPER"
ln -sf terrasatch-edge "$PKGROOT/usr/local/bin/tsedge"

cat > "$UNIT_DIR/terrasatch-edge.service" <<'UNIT'
[Unit]
Description=TerraSatch Edge
Documentation=https://www.terrasatch.com/downloads
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/terrasatch-edge run
Restart=on-failure
RestartSec=5
Environment=TERRASATCH_EDGE_CONFIG_DIR=/etc/terrasatch-edge
Environment=TERRASATCH_EDGE_STATE_DIR=/var/lib/terrasatch-edge
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
UNIT

cat > "$PKGROOT/DEBIAN/control" <<EOF
Package: terrasatch-edge
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: TerraSatch
Recommends: rtl-sdr
Description: TerraSatch Edge field runtime
 Local runtime for TerraSatch device pairing, hardware health, configuration,
 radio receiver adapters, and the TerraListen field workflow.
EOF

cat > "$PKGROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
install -d -m 0700 /etc/terrasatch-edge
install -d -m 0700 /var/lib/terrasatch-edge
install -d -m 0700 /var/lib/terrasatch-edge/logs
systemctl daemon-reload || true
systemctl enable terrasatch-edge.service || true
systemctl restart terrasatch-edge.service || systemctl start terrasatch-edge.service || true
cat <<'MSG'
TerraSatch Edge installed.

Pair this field computer once with:
  sudo terrasatch-edge setup

Then verify:
  sudo terrasatch-edge status
  sudo terrasatch-edge doctor

The service watches the same system registration and will pick up pairing changes without a reinstall.
MSG
EOF

cat > "$PKGROOT/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "deconfigure" ]; then
  systemctl stop terrasatch-edge.service || true
  systemctl disable terrasatch-edge.service || true
fi
EOF

cat > "$PKGROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
systemctl daemon-reload || true
# Registration/config are intentionally preserved in /etc/terrasatch-edge and
# /var/lib/terrasatch-edge across package removal/reinstall.
EOF

chmod 755 "$PKGROOT/DEBIAN/postinst" "$PKGROOT/DEBIAN/prerm" "$PKGROOT/DEBIAN/postrm"
chmod 700 "$CONFIG_DIR" "$STATE_DIR" "$LOG_DIR"

mkdir -p release
ARTIFACT="$ROOT/release/terrasatch-edge_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$PKGROOT" "$ARTIFACT"

if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
else
  SHA256="$($PYTHON -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$ARTIFACT")"
fi

echo
echo "Built: $ARTIFACT"
echo "Architecture: $ARCH"
echo "Version: $VERSION"
echo "SHA256: $SHA256"
echo "RTL-SDR tooling is a recommended Debian package and remains receive-only in the current public Edge runtime."
