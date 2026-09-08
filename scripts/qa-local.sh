#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
QA_CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/terrasatch"
VENV_DIR="${TERRASATCH_QA_VENV:-$QA_CACHE_ROOT/edge-qa-venv}"
COVERAGE_XML="$QA_CACHE_ROOT/edge-changed-code-coverage.xml"
WITH_SPEECH="${TERRASATCH_QA_WITH_SPEECH:-0}"

# QA must not inherit production credentials or call the production API.
export TERRASATCH_EDGE_API_URL=http://127.0.0.1:18000
unset TERRASATCH_EDGE_API_KEY || true
QA_STATE_ROOT="$(mktemp -d)"
trap 'rm -rf "$QA_STATE_ROOT"' EXIT
export TERRASATCH_EDGE_CONFIG_DIR="$QA_STATE_ROOT/config"
export TERRASATCH_EDGE_STATE_DIR="$QA_STATE_ROOT/state"
export NO_PROXY="127.0.0.1,localhost,${NO_PROXY:-}"

printf '\nTerraSatch Edge local QA\n'
printf 'Repository: %s\n' "$ROOT"
printf 'QA venv: %s\n' "$VENV_DIR"
printf 'Python: '
"$PYTHON_BIN" --version

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version}")
PY

mkdir -p "$QA_CACHE_ROOT"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
if [[ "$WITH_SPEECH" == "1" ]]; then
  python -m pip install -e '.[dev,ui,speech]'
else
  python -m pip install -e '.[dev,ui]'
fi
python -m pip check

git diff --check

printf '\n[1/7] Ruff\n'
ruff check src tests

printf '\n[2/7] Compile/import smoke\n'
python -m compileall -q src tests
python - <<'PY'
import terrasatch_edge
from terrasatch_edge.cli import app
from terrasatch_edge.ingest import ingest_audio_file
from terrasatch_edge.speech import FasterWhisperSpeechProvider
print(f"terrasatch-edge {terrasatch_edge.__version__} imports OK")
print(f"CLI object: {type(app).__name__}")
print(f"Speech provider: {FasterWhisperSpeechProvider.name}")
print(f"Canonical audio ingest: {ingest_audio_file.__name__}")
PY

printf '\n[3/7] Complete repository regression suite\n'
pytest

printf '\n[4/7] Changed speech/ingest/config coverage gate (>=75%%)\n'
pytest \
  --cov=terrasatch_edge.speech \
  --cov=terrasatch_edge.ingest \
  --cov=terrasatch_edge.config \
  --cov-report=term-missing \
  --cov-report="xml:$COVERAGE_XML" \
  --cov-fail-under=75

printf '\nNote: full-package coverage is not used as the release gate yet because the pre-existing\nCLI/discovery/doctor/local_ui modules were never covered to the repository-wide 75%% target.\nThe full regression suite above still executes every repository test; the coverage gate applies\nto the speech-ingestion/config surface introduced or materially changed in Edge 0.2.0.\n'

printf '\n[5/7] Command/TX coverage gate (>=90%%)\n'
pytest \
  --cov=terrasatch_edge.commands \
  --cov=terrasatch_edge.radio_execution \
  --cov=terrasatch_edge.command_journal \
  --cov=terrasatch_edge.tx_bridge \
  --cov-report=term-missing \
  --cov-fail-under=90

printf '\n[6/7] CLI smoke\n'
terrasatch-edge --help >/dev/null
terrasatch-edge ingest-audio --help >/dev/null
terrasatch-edge version

printf '\n[7/7] Optional speech dependency smoke\n'
if [[ "$WITH_SPEECH" == "1" ]]; then
  python - <<'PY'
import faster_whisper
print("faster-whisper import OK")
PY
else
  printf 'Skipped model runtime dependency install. Set TERRASATCH_QA_WITH_SPEECH=1 to include it.\n'
fi

printf '\nPASS: TerraSatch Edge full local QA completed successfully.\n'
