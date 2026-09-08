#!/usr/bin/env bash
set -euo pipefail
EDGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_ROOT="${1:?Usage: qa-api-compatibility.sh API_CHECKOUT EXPECT_TX_0_OR_1}"
EXPECT_TX="${2:?Specify 0 for current API or 1 for transmitted-result API}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$API_ROOT/src:$API_ROOT/tests/unit:$EDGE_ROOT/src"
export TERRASATCH_JOINT_EXPECT_TX="$EXPECT_TX"
export TERRASATCH_ENVIRONMENT=local
export TERRASATCH_INTELLIGENCE_PROVIDER=deterministic
export TERRASATCH_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:55432/test
export TERRASATCH_REDIS_URL=redis://127.0.0.1:56379/15
unset TERRASATCH_EDGE_API_KEY || true
RESULT_DIR="$(mktemp -d)"
trap 'rm -rf "$RESULT_DIR"' EXIT
"$PYTHON_BIN" -c 'import terrasatch, terrasatch_edge; print("API and Edge imported")'
"$PYTHON_BIN" -m pytest -q "$EDGE_ROOT/compatibility/test_api_edge.py" --junitxml="$RESULT_DIR/joint.xml"
"$PYTHON_BIN" - "$RESULT_DIR/joint.xml" <<'PY'
import sys
from xml.etree import ElementTree
root = ElementTree.parse(sys.argv[1]).getroot()
cases = root.findall('.//testcase')
assert len(cases) == 4
assert not root.findall('.//failure') and not root.findall('.//error') and not root.findall('.//skipped')
print(f'PASS: {len(cases)} API/Edge compatibility scenarios')
PY
