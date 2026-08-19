#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS package verification must run on macOS." >&2
  exit 1
fi

PKG="${1:-}"
EXPECTED_ARCH="${2:-}"
EXPECTED_VERSION="${3:-0.2.2}"

if [[ -z "$PKG" || -z "$EXPECTED_ARCH" ]]; then
  echo "Usage: $0 <package.pkg> <arm64|x64> [version]" >&2
  exit 2
fi
if [[ ! -f "$PKG" ]]; then
  echo "Package not found: $PKG" >&2
  exit 2
fi

case "$EXPECTED_ARCH" in
  arm64) MACH_PATTERN="arm64" ;;
  x64|x86_64) MACH_PATTERN="x86_64" ;;
  *)
    echo "Unsupported expected architecture: $EXPECTED_ARCH" >&2
    exit 2
    ;;
esac

ROOT="$(cd "$(dirname "$PKG")/.." && pwd)"
mkdir -p "$ROOT/release"
PAYLOAD_LOG="$ROOT/release/macos-${EXPECTED_ARCH}-payload.txt"
SIGNATURE_LOG="$ROOT/release/macos-${EXPECTED_ARCH}-signature.txt"
STATUS_LOG="$ROOT/release/macos-${EXPECTED_ARCH}-status.json"
DOCTOR_LOG="$ROOT/release/macos-${EXPECTED_ARCH}-doctor.txt"
LAUNCHD_LOG="$ROOT/release/macos-${EXPECTED_ARCH}-launchd.txt"

printf 'Package: %s\n' "$PKG"
printf 'SHA-256: '
shasum -a 256 "$PKG"

echo "Checking package payload..."
pkgutil --payload-files "$PKG" | tee "$PAYLOAD_LOG"
grep -E '(^|/)usr/local/bin/terrasatch-edge$' "$PAYLOAD_LOG" >/dev/null
grep -E '(^|/)Library/LaunchDaemons/com\.terrasatch\.edge\.plist$' "$PAYLOAD_LOG" >/dev/null
grep -E '(^|/)usr/local/lib/terrasatch-edge/TerraSatchEdge$' "$PAYLOAD_LOG" >/dev/null

echo "Recording package signature state..."
(pkgutil --check-signature "$PKG" || true) 2>&1 | tee "$SIGNATURE_LOG"

echo "Installing package on disposable macOS verifier..."
sudo installer -pkg "$PKG" -target /

CLI="/usr/local/bin/terrasatch-edge"
BIN="/usr/local/lib/terrasatch-edge/TerraSatchEdge"
PLIST="/Library/LaunchDaemons/com.terrasatch.edge.plist"

[[ -x "$CLI" ]] || { echo "Installed CLI is missing: $CLI" >&2; exit 1; }
[[ -x "$BIN" ]] || { echo "Installed executable is missing: $BIN" >&2; exit 1; }
[[ -f "$PLIST" ]] || { echo "LaunchDaemon plist is missing: $PLIST" >&2; exit 1; }

VERSION_OUTPUT="$($CLI --version)"
echo "$VERSION_OUTPUT"
[[ "$VERSION_OUTPUT" == "terrasatch-edge $EXPECTED_VERSION" ]] || {
  echo "Unexpected installed version: $VERSION_OUTPUT" >&2
  exit 1
}

BIN_INFO="$(file "$BIN")"
echo "$BIN_INFO"
[[ "$BIN_INFO" == *"$MACH_PATTERN"* ]] || {
  echo "Installed executable does not contain expected architecture $MACH_PATTERN." >&2
  exit 1
}

codesign --verify --deep --strict "$BIN"
plutil -lint "$PLIST"

sudo launchctl print system/com.terrasatch.edge | tee "$LAUNCHD_LOG"

# The native package intentionally stores configuration and credentials under a
# root-owned 0700 system directory so the LaunchDaemon and administrative CLI
# share one protected registration. Run stateful diagnostics with the same
# privileges expected by the installed package documentation.
sudo "$CLI" status --json | tee "$STATUS_LOG"
sudo "$CLI" doctor | tee "$DOCTOR_LOG"

echo "macOS package verification passed for $EXPECTED_ARCH v$EXPECTED_VERSION."
