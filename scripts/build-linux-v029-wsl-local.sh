#!/usr/bin/env bash
# Run on Ubuntu 24.04 AMD64 (e.g., WSL2). No GitHub Actions or production API.
# bash build-linux-v029-wsl-local.sh /mnt/c/Users/<user>/Downloads/TerraSatch-Edge-QA/linux-v029
set -Eeuo pipefail
SHA=f3918dd023e3862eb9bd4dc183be4c6cbeb36644
NAME=terrasatch-edge_0.2.9_amd64.deb
die() { echo "ERROR: $*" >&2; exit 1; }
[[ $# -eq 1 && "$1" = /* ]] || die "Pass an absolute output-directory path."
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 ]] || die "Ubuntu 24.04 is required (got ${PRETTY_NAME:-unknown})."
[[ "$(dpkg --print-architecture)" == amd64 && "$(uname -m)" == x86_64 ]] || die "AMD64 is required."
for c in python3 git dpkg-deb sha256sum; do command -v "$c" >/dev/null || die "Missing $c."; done
python3 -c 'import sys; assert sys.version_info >= (3,12)' || die "Python 3.12+ required."
OUT="$1"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd -P)"
[[ ! -e "$OUT/$NAME" ]] || die "Output already exists: $OUT/$NAME. Refusing to overwrite."
WORK="$(mktemp -d "${TMPDIR:-/tmp}/tsedge-v029.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export TERRASATCH_EDGE_API_URL=http://127.0.0.1:18000
unset TERRASATCH_EDGE_API_KEY TERRASATCH_API_KEY || true
export TERRASATCH_EDGE_CONFIG_DIR="$WORK/config"
export TERRASATCH_EDGE_STATE_DIR="$WORK/state"
export XDG_CACHE_HOME="$WORK/cache"
export PIP_NO_INPUT=1 PIP_DISABLE_PIP_VERSION_CHECK=1
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"

echo "[1/5] Clone exact v0.2.9 source into isolated Linux build directory"
git clone -q --depth 1 --branch release/edge-v0.2.9-windows-beta \
  https://github.com/k3y10/terrasatch-edge.git "$WORK/src"
cd "$WORK/src"
[[ "$(git rev-parse HEAD)" == "$SHA" ]] || die "Git SHA mismatch: source branch moved."
grep -Eq '^version[[:space:]]*=[[:space:]]*"0\.2\.9"[[:space:]]*$' pyproject.toml || die "Source is not version 0.2.9."
python3 -m venv "$WORK/venv-check" || die "Install python3.12-venv."
echo "[2/5] Full unit tests, native PyInstaller build, branded Debian packaging"
PYTHON_BIN=python3 bash scripts/build-linux-deb.sh
DEB="$PWD/release/$NAME"
[[ -s "$DEB" ]] || die "No v0.2.9 package produced."

echo "[3/5] Inspect the Debian package's metadata and services"
[[ "$(dpkg-deb -f "$DEB" Package)" == terrasatch-edge ]] || die "Wrong package identity."
[[ "$(dpkg-deb -f "$DEB" Version)" == 0.2.9 ]] || die "Wrong package version."
[[ "$(dpkg-deb -f "$DEB" Architecture)" == amd64 ]] || die "Wrong architecture."
dpkg-deb --contents "$DEB" > "$WORK/files.txt"
grep -qE '\./opt/terrasatch-edge/terrasatch-edge$' "$WORK/files.txt" || die "Missing binary."
grep -q 'terrasatch-edge.service' "$WORK/files.txt" || die "Missing Edge service."
grep -q 'terrasatch-radio.service' "$WORK/files.txt" || die "Missing radio service."
dpkg-deb --control "$DEB" "$WORK/control"
if grep -Eq 'systemctl[[:space:]]+enable([[:space:]]+--now)?[[:space:]]+terrasatch-radio\.service' "$WORK/control/postinst"; then
  die "Unexpected radio autostart."
fi

echo "[4/5] Extract and smoke-test the packaged Linux executable (no installation)"
dpkg-deb --extract "$DEB" "$WORK/payload"
"$WORK/payload/opt/terrasatch-edge/terrasatch-edge" --version

echo "[5/5] Copy verified .deb, checksums and build metadata to output"
SUM="$(sha256sum "$DEB" | cut -d' ' -f1)"
cp "$DEB" "$OUT/$NAME"
[[ "$(sha256sum "$OUT/$NAME" | cut -d' ' -f1)" == "$SUM" ]] || die "Copy hash mismatch."
printf '%s  %s\n' "$SUM" "$NAME" > "$OUT/SHA256SUMS-LINUX.txt"
cat > "$OUT/LINUX-V029-BUILD-METADATA.txt" <<META
release_version=0.2.9
package_filename=$NAME
package_sha256=$SUM
source_commit=$SHA
build_os=Ubuntu 24.04
architecture=amd64
full_pytest=passed
pyinstaller_branding_check=passed
debian_metadata_and_services=passed
extracted_binary_smoke=passed
radio_autostart=disabled
native_systemd_install_and_reboot=not_tested
build_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
META
echo "PASS: Linux AMD64 v0.2.9 build and extracted package smoke succeeded."
echo "Debian file: $OUT/$NAME"
echo "SHA256: $SUM"
echo "No GitHub Actions and no production API were used."
echo "Important: native systemd install and reboot testing are still separate gates."
