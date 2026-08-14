#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${TERRASATCH_EDGE_PREFIX:-$HOME/.local/share/terrasatch-edge}"
VENV="$PREFIX/venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required." >&2
  exit 1
fi

mkdir -p "$PREFIX"
"$PYTHON_BIN" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install "$ROOT[serial,usb,ui]"

mkdir -p "$HOME/.local/bin"
ln -sf "$VENV/bin/terrasatch-edge" "$HOME/.local/bin/terrasatch-edge"
ln -sf "$VENV/bin/tsedge" "$HOME/.local/bin/tsedge"

cat <<MSG
TerraSatch Edge installed.

Run:
  terrasatch-edge setup
  terrasatch-edge doctor

If ~/.local/bin is not on PATH, add it to your shell profile.
MSG
