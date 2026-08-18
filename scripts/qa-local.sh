#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${TERRASATCH_QA_VENV:-.venv-qa}"
WITH_SPEECH="${TERRASATCH_QA_WITH_SPEECH:-0}"

printf '\nTerraSatch Edge local QA\n'
printf 'Repository: %s\n' "$ROOT"
printf 'Python: '
"$PYTHON_BIN" --version

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version}")
PY

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
if [[ "$WITH_SPEECH" == "1" ]]; then
  python -m pip install -e '.[dev,speech]'
else
  python -m pip install -e '.[dev]'
fi

printf '\n[1/5] Ruff\n'
ruff check src tests

printf '\n[2/5] Compile/import smoke\n'
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

printf '\n[3/5] Full pytest + project coverage threshold\n'
pytest --cov=terrasatch_edge --cov-report=term-missing --cov-report=xml

printf '\n[4/5] CLI smoke\n'
terrasatch-edge --help >/dev/null
terrasatch-edge ingest-audio --help >/dev/null
terrasatch-edge version

printf '\n[5/5] Optional speech dependency smoke\n'
if [[ "$WITH_SPEECH" == "1" ]]; then
  python - <<'PY'
import faster_whisper
print("faster-whisper import OK")
PY
else
  printf 'Skipped model runtime dependency install. Set TERRASATCH_QA_WITH_SPEECH=1 to include it.\n'
fi

printf '\nPASS: TerraSatch Edge full local QA completed successfully.\n'
