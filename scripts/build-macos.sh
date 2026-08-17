#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "The macOS package must be built on macOS." >&2
  exit 1
fi
if ! command -v pkgbuild >/dev/null 2>&1; then
  echo "pkgbuild is required (install the current Xcode Command Line Tools)." >&2
  exit 1
fi

BUILD_VENV="$ROOT/.build-venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required to build TerraSatch Edge." >&2
  exit 1
fi
if [[ ! -d "$BUILD_VENV" ]]; then
  "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi
PYTHON="$BUILD_VENV/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -e '.[serial,usb,ui,build,dev]'

VERSION="$($PYTHON -c 'import terrasatch_edge; print(terrasatch_edge.__version__)')"
MACHINE="$(uname -m)"
case "$MACHINE" in
  arm64) ARCH="arm64" ;;
  x86_64) ARCH="x64" ;;
  *)
    echo "Unsupported public pilot architecture: $MACHINE (expected arm64 or x86_64)." >&2
    exit 1
    ;;
esac

"$PYTHON" -m pytest
rm -rf build dist release/macos-root release/macos-scripts

PYINSTALLER_ARGS=(
  --noconfirm
  --clean
  --onedir
  --name TerraSatchEdge
  --collect-all uvicorn
  --collect-all fastapi
)
if [[ -n "${TERRASATCH_MACOS_APPLICATION_IDENTITY:-}" ]]; then
  PYINSTALLER_ARGS+=(--codesign-identity "$TERRASATCH_MACOS_APPLICATION_IDENTITY")
fi
PYINSTALLER_ARGS+=(packaging/entrypoints/edge_cli.py)
"$PYTHON" -m PyInstaller "${PYINSTALLER_ARGS[@]}"

PKGROOT="$ROOT/release/macos-root"
SCRIPTS="$ROOT/release/macos-scripts"
INSTALL_ROOT="$PKGROOT/usr/local/lib/terrasatch-edge"
WRAPPER="$PKGROOT/usr/local/bin/terrasatch-edge"
APP_SUPPORT="$PKGROOT/Library/Application Support/TerraSatch/Edge"
LOG_DIR="$PKGROOT/Library/Logs/TerraSatch/Edge"
PLIST="$PKGROOT/Library/LaunchDaemons/com.terrasatch.edge.plist"

mkdir -p \
  "$INSTALL_ROOT" \
  "$(dirname "$WRAPPER")" \
  "$APP_SUPPORT/state" \
  "$LOG_DIR" \
  "$(dirname "$PLIST")" \
  "$SCRIPTS"
cp -R dist/TerraSatchEdge/. "$INSTALL_ROOT/"

cat > "$WRAPPER" <<'EOF'
#!/bin/sh
export TERRASATCH_EDGE_CONFIG_DIR="/Library/Application Support/TerraSatch/Edge"
export TERRASATCH_EDGE_STATE_DIR="/Library/Application Support/TerraSatch/Edge/state"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin${PATH:+:$PATH}"
exec /usr/local/lib/terrasatch-edge/TerraSatchEdge "$@"
EOF
chmod 755 "$WRAPPER"
ln -sf terrasatch-edge "$PKGROOT/usr/local/bin/tsedge"

cat > "$PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.terrasatch.edge</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/terrasatch-edge</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TERRASATCH_EDGE_CONFIG_DIR</key>
    <string>/Library/Application Support/TerraSatch/Edge</string>
    <key>TERRASATCH_EDGE_STATE_DIR</key>
    <string>/Library/Application Support/TerraSatch/Edge/state</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>/Library/Logs/TerraSatch/Edge/edge.log</string>
  <key>StandardErrorPath</key>
  <string>/Library/Logs/TerraSatch/Edge/edge-error.log</string>
</dict>
</plist>
PLIST
chmod 644 "$PLIST"

cat > "$SCRIPTS/postinstall" <<'EOF'
#!/bin/sh
set -e
CONFIG_DIR="/Library/Application Support/TerraSatch/Edge"
STATE_DIR="$CONFIG_DIR/state"
LOG_DIR="/Library/Logs/TerraSatch/Edge"
PLIST="/Library/LaunchDaemons/com.terrasatch.edge.plist"

install -d -m 0700 "$CONFIG_DIR" "$STATE_DIR"
install -d -m 0755 "$LOG_DIR"
chown -R root:wheel "$CONFIG_DIR" "$LOG_DIR" || true
chmod 644 "$PLIST"
chown root:wheel "$PLIST" || true

launchctl bootout system "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap system "$PLIST" || true
launchctl enable system/com.terrasatch.edge || true
launchctl kickstart -k system/com.terrasatch.edge || true

cat <<'MSG'
TerraSatch Edge installed.

Pair this Mac once with:
  sudo terrasatch-edge setup

Then verify:
  sudo terrasatch-edge status
  sudo terrasatch-edge doctor

For RTL-SDR/Nooelec receive testing, install rtl-sdr tools in /opt/homebrew/bin
(Apple Silicon) or /usr/local/bin (Intel). The service checks both locations.
MSG
EOF
chmod 755 "$SCRIPTS/postinstall"

mkdir -p release
UNSIGNED="$ROOT/release/TerraSatch-Edge-${VERSION}-macOS-${ARCH}-unsigned.pkg"
FINAL="$ROOT/release/TerraSatch-Edge-${VERSION}-macOS-${ARCH}.pkg"
rm -f "$UNSIGNED" "$FINAL"

pkgbuild \
  --root "$PKGROOT" \
  --scripts "$SCRIPTS" \
  --identifier com.terrasatch.edge \
  --version "$VERSION" \
  --install-location / \
  "$UNSIGNED"

if [[ -n "${TERRASATCH_MACOS_INSTALLER_IDENTITY:-}" ]]; then
  productsign \
    --sign "$TERRASATCH_MACOS_INSTALLER_IDENTITY" \
    "$UNSIGNED" \
    "$FINAL"
  rm -f "$UNSIGNED"
else
  mv "$UNSIGNED" "$FINAL"
fi

if [[ -n "${TERRASATCH_MACOS_NOTARY_PROFILE:-}" ]]; then
  if [[ -z "${TERRASATCH_MACOS_INSTALLER_IDENTITY:-}" ]]; then
    echo "TERRASATCH_MACOS_NOTARY_PROFILE requires a signed installer." >&2
    exit 1
  fi
  xcrun notarytool submit "$FINAL" \
    --keychain-profile "$TERRASATCH_MACOS_NOTARY_PROFILE" \
    --wait
  xcrun stapler staple "$FINAL"
  xcrun stapler validate "$FINAL"
fi

SHA256="$(shasum -a 256 "$FINAL" | awk '{print $1}')"
echo
echo "Built: $FINAL"
echo "Architecture: $ARCH"
echo "Version: $VERSION"
echo "SHA256: $SHA256"
if [[ -z "${TERRASATCH_MACOS_INSTALLER_IDENTITY:-}" ]]; then
  echo "Pilot package is unsigned. Do not publish broadly until Developer ID signing and notarization are completed."
elif [[ -z "${TERRASATCH_MACOS_NOTARY_PROFILE:-}" ]]; then
  echo "Installer is signed but not notarized. Notarize and staple before broad public distribution."
else
  echo "Installer signing, notarization, and stapling completed."
fi
