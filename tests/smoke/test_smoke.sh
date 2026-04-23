#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
SPLUNK_PYTHON="${SPLUNK_PYTHON:-$SPLUNK_HOME/bin/python3.9}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

echo "== ai_lab smoke test =="

echo "[1/3] Static and syntax checks"
if [[ ! -x "$SPLUNK_PYTHON" ]]; then
  fail "Expected interpreter not found: $SPLUNK_PYTHON"
fi

"$SPLUNK_PYTHON" -m py_compile \
  "$ROOT_DIR/bin/launcher.py" \
  "$ROOT_DIR/bin/backfill_log.py" \
  "$ROOT_DIR/bin/live_log.py" \
  "$ROOT_DIR/bin/scenario_control.py" \
  "$ROOT_DIR/bin/workshop_region.py"

echo "PASS: Python compile checks"

echo "[2/3] Runtime preconditions"
[[ -x "$SPLUNK_BIN" ]] || fail "Splunk CLI not found at $SPLUNK_BIN"
[[ -f "$ROOT_DIR/default/inputs.conf" ]] || fail "Missing default/inputs.conf"
[[ -f "$ROOT_DIR/default/indexes.conf" ]] || fail "Missing default/indexes.conf"
[[ -f "$ROOT_DIR/default/ai_lab_scenarios.conf" ]] || fail "Missing default/ai_lab_scenarios.conf"
[[ -f "$ROOT_DIR/default/data/ui/views/workshop_introduction.xml" ]] || fail "Missing workshop_introduction view"
[[ -f "$ROOT_DIR/default/data/ui/views/scenario_control.xml" ]] || fail "Missing scenario_control view"
[[ -f "$ROOT_DIR/samples/thousandeyes/cisco:thousandeyes:metric/sample.json" ]] || fail "Missing thousandeyes sample"
[[ -f "$ROOT_DIR/samples/telemetry/cnc_interface_counter_json/sample.json" ]] || fail "Missing telemetry sample"

echo "PASS: Runtime preconditions"

echo "[3/3] Splunk SPL assertions"
bash "$ROOT_DIR/tests/splunk/run_spl_checks.sh"

echo "Smoke test passed."
