#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(awk -F'"' '/^version = / {print $2; exit}' pyproject.toml)"
[[ -n "$VERSION" ]] || { echo "Unable to determine TerraSatch Edge version." >&2; exit 1; }
SOURCE_REVISION="$(git rev-parse HEAD)"
HOST_MACHINE="$(uname -m)"
TARGET_ARCH="${TERRASATCH_MACOS_TARGET_ARCH:-$HOST_MACHINE}"
case "$TARGET_ARCH" in
  arm64) ARCH="arm64" ;;
  x64|x86_64) ARCH="x64" ;;
  *) echo "Unsupported macOS target architecture: $TARGET_ARCH" >&2; exit 1 ;;
esac

echo "TerraSatch Edge Partner Beta build"
echo "Version: $VERSION"
echo "Channel: PARTNER BETA"
echo "Integrity: SHA-256 checksum will be generated"
echo "This is not the official signed/notarized TerraSatch Edge release."
echo

./scripts/build-macos.sh

SOURCE="$ROOT/release/TerraSatch-Edge-${VERSION}-macOS-${ARCH}.pkg"
[[ -f "$SOURCE" ]] || { echo "Expected macOS package not found: $SOURCE" >&2; exit 1; }

if pkgutil --check-signature "$SOURCE" >/dev/null 2>&1; then
  SIGNATURE_STATE="signed"
  SUFFIX="partner-beta-signed"
else
  SIGNATURE_STATE="unsigned"
  SUFFIX="partner-beta-unsigned"
fi

BETA_NAME="TerraSatch-Edge-${VERSION}-macOS-${ARCH}-${SUFFIX}.pkg"
BETA="$ROOT/release/$BETA_NAME"
rm -f "$BETA" "$BETA.sha256" "$BETA.release.json" "$SOURCE.sha256"
mv "$SOURCE" "$BETA"
SHA256="$(shasum -a 256 "$BETA" | awk '{print $1}')"
printf '%s  %s\n' "$SHA256" "$BETA_NAME" > "$BETA.sha256"

python3 - "$BETA.release.json" "$VERSION" "$SIGNATURE_STATE" "$SHA256" "$SOURCE_REVISION" "$BETA_NAME" <<'PY'
import json
import sys
from pathlib import Path

path, version, signature, sha256, revision, artifact = sys.argv[1:]
payload = {
    "product": "TerraSatch Edge",
    "version": version,
    "channel": "partner-beta",
    "intended_use": "controlled testing and evaluation",
    "official_release": False,
    "code_signature": signature,
    "integrity": "sha256",
    "sha256": sha256,
    "source_revision": revision,
    "artifact": artifact,
    "notice": "Not the official TerraSatch Edge release. Gatekeeper or publisher warnings may appear until the official signing/notarization gate is complete.",
}
Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

echo
echo "Partner Beta artifact ready:"
echo "  $BETA"
echo "  $BETA.sha256"
echo "  $BETA.release.json"
echo "Code signature state: $SIGNATURE_STATE"
echo "SHA256: $SHA256"
echo "Distribution: controlled beta / partner evaluation only; not an Official Release."
