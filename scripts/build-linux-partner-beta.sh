#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(awk -F'"' '/^version = / {print $2; exit}' pyproject.toml)"
[[ -n "$VERSION" ]] || { echo "Unable to determine TerraSatch Edge version." >&2; exit 1; }
SOURCE_REVISION="$(git rev-parse HEAD)"
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64|arm64) ;;
  *) echo "Unsupported Partner Beta Linux architecture: $ARCH" >&2; exit 1 ;;
esac

echo "TerraSatch Edge Partner Beta build"
echo "Version: $VERSION"
echo "Channel: PARTNER BETA"
echo "Package signing: not configured in the current Linux pilot pipeline"
echo "Integrity: SHA-256 checksum will be generated"
echo "This is not the official TerraSatch Edge release."
echo

./scripts/build-linux-deb.sh

SOURCE="$ROOT/release/terrasatch-edge_${VERSION}_${ARCH}.deb"
[[ -f "$SOURCE" ]] || { echo "Expected Linux package not found: $SOURCE" >&2; exit 1; }

BETA_NAME="terrasatch-edge_${VERSION}_partner-beta_${ARCH}.deb"
BETA="$ROOT/release/$BETA_NAME"
rm -f "$BETA" "$BETA.sha256" "$BETA.release.json"
mv "$SOURCE" "$BETA"
SHA256="$(sha256sum "$BETA" | awk '{print $1}')"
printf '%s  %s\n' "$SHA256" "$BETA_NAME" > "$BETA.sha256"

python3 - "$BETA.release.json" "$VERSION" "$SHA256" "$SOURCE_REVISION" "$BETA_NAME" <<'PY'
import json
import sys
from pathlib import Path

path, version, sha256, revision, artifact = sys.argv[1:]
payload = {
    "product": "TerraSatch Edge",
    "version": version,
    "channel": "partner-beta",
    "intended_use": "controlled testing and evaluation",
    "official_release": False,
    "code_signature": "not-configured",
    "integrity": "sha256",
    "sha256": sha256,
    "source_revision": revision,
    "artifact": artifact,
    "notice": "Partner Beta package. SHA-256 verifies artifact integrity but is not a publisher/code signature.",
}
Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

echo
echo "Partner Beta artifact ready:"
echo "  $BETA"
echo "  $BETA.sha256"
echo "  $BETA.release.json"
echo "SHA256: $SHA256"
echo "Distribution: controlled beta / partner evaluation only; not an Official Release."
