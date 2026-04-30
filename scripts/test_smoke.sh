#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
SPLUNK_PYTHON="${SPLUNK_PYTHON:-$SPLUNK_HOME/bin/python3.9}"
SPLUNK_APP="${SPLUNK_APP:-ai_lab}"
SPLUNK_AUTH="${SPLUNK_AUTH:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-${AUTH_TOKEN:-}}"
INDEX_CONF="$ROOT_DIR/default/indexes.conf"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

run_search() {
  local query="$1"
  if [[ -n "$SPLUNK_TOKEN" ]]; then
    "$SPLUNK_BIN" search "$query" -app "$SPLUNK_APP" -token "$SPLUNK_TOKEN"
  else
    "$SPLUNK_BIN" search "$query" -app "$SPLUNK_APP" -auth "$SPLUNK_AUTH"
  fi
}

extract_count() {
  awk '
    /^[[:space:]]*[0-9]+[[:space:]]*$/ { val=$1 }
    END {
      if (val == "") exit 1
      print val
    }
  '
}

assert_count_eq() {
  local label="$1"
  local query="$2"
  local expected="$3"
  local count

  if ! count="$(run_search "$query" | extract_count)"; then
    fail "$label query failed or did not return a numeric count"
  fi
  if (( count != expected )); then
    fail "$label expected $expected, got $count"
  fi
  echo "PASS: $label = $count"
}

load_app_indexes() {
  awk '
    /^\[/ && /\]$/ {
      name=$0
      gsub(/^\[/, "", name)
      gsub(/\]$/, "", name)
      if (name != "") print name
    }
  ' "$INDEX_CONF"
}

echo "== ai_lab smoke test =="

echo "[1/4] Static and syntax checks"
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

echo "[2/4] Runtime preconditions"
[[ -x "$SPLUNK_BIN" ]] || fail "Splunk CLI not found at $SPLUNK_BIN"
[[ -f "$ROOT_DIR/default/inputs.conf" ]] || fail "Missing default/inputs.conf"
[[ -f "$ROOT_DIR/default/indexes.conf" ]] || fail "Missing default/indexes.conf"
[[ -f "$ROOT_DIR/default/ai_lab_scenarios.conf" ]] || fail "Missing default/ai_lab_scenarios.conf"
[[ -f "$ROOT_DIR/default/data/ui/views/workshop_introduction.xml" ]] || fail "Missing workshop_introduction view"
[[ -f "$ROOT_DIR/default/data/ui/views/scenario_control.xml" ]] || fail "Missing scenario_control view"
[[ -f "$ROOT_DIR/samples/thousandeyes/cisco:thousandeyes:metric/sample.json" ]] || fail "Missing thousandeyes sample"
[[ -f "$ROOT_DIR/samples/telemetry/cnc_interface_counter_json/sample.json" ]] || fail "Missing telemetry sample"
[[ -f "$INDEX_CONF" ]] || fail "Missing default/indexes.conf"
[[ -n "$SPLUNK_AUTH" || -n "$SPLUNK_TOKEN" ]] || fail "SPLUNK_AUTH or SPLUNK_TOKEN is required"

echo "PASS: Runtime preconditions"

echo "[3/4] Spool directory is empty"
SPOOL_DIR="$ROOT_DIR/var/spool/ai_lab"
if [[ -d "$SPOOL_DIR" ]]; then
  spool_count="$(find "$SPOOL_DIR" -type f 2>/dev/null | wc -l | tr -d '[:space:]')"
  if (( spool_count != 0 )); then
    fail "Spool dir not empty: $spool_count file(s) found under $SPOOL_DIR"
  fi
  echo "PASS: Spool dir is empty ($SPOOL_DIR)"
else
  echo "PASS: Spool dir does not exist ($SPOOL_DIR)"
fi

echo "[4/4] Reset-readiness SPL assertions (empty-state)"
while IFS= read -r idx; do
  [[ -n "$idx" ]] || continue
  assert_count_eq \
    "Index '$idx' is empty" \
    "earliest=0 latest=now index=$idx | stats count as count" \
    0
done < <(load_app_indexes)

echo "Smoke test passed."
