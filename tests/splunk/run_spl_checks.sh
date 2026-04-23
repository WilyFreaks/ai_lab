#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
SPLUNK_APP="${SPLUNK_APP:-ai_lab}"
SPLUNK_AUTH="${SPLUNK_AUTH:-}"
TIME_WINDOW="${TIME_WINDOW:-24h}"
INDEX_CONF="$ROOT_DIR/default/indexes.conf"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

run_search() {
  local query="$1"
  "$SPLUNK_BIN" search "$query" -app "$SPLUNK_APP" -auth "$SPLUNK_AUTH"
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

assert_count_ge() {
  local label="$1"
  local query="$2"
  local minimum="$3"
  local count

  if ! count="$(run_search "$query" | extract_count)"; then
    fail "$label query failed or did not return a numeric count"
  fi

  if (( count < minimum )); then
    fail "$label expected >= $minimum, got $count"
  fi

  echo "PASS: $label = $count"
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
  if [[ ! -f "$INDEX_CONF" ]]; then
    fail "Missing index config: $INDEX_CONF"
  fi

  awk '
    /^\[/ && /\]$/ {
      name=$0
      gsub(/^\[/, "", name)
      gsub(/\]$/, "", name)
      if (name != "") print name
    }
  ' "$INDEX_CONF"
}

if [[ ! -x "$SPLUNK_BIN" ]]; then
  fail "Splunk CLI not found at $SPLUNK_BIN"
fi

if [[ -z "$SPLUNK_AUTH" ]]; then
  fail "SPLUNK_AUTH is required (example: export SPLUNK_AUTH='admin:changeme')"
fi

echo "Running SPL checks (app=$SPLUNK_APP, window=$TIME_WINDOW, transport=splunk-cli)..."

# Hard precondition: all app indexes must be empty before test run.
while IFS= read -r idx; do
  [[ -n "$idx" ]] || continue
  assert_count_eq \
    "Index '$idx' is empty" \
    "index=$idx | stats count as count" \
    0
done < <(load_app_indexes)

assert_count_eq \
  "No JSON/parser errors from ai_lab ingest paths" \
  "index=_internal earliest=-$TIME_WINDOW (sourcetype=splunkd OR sourcetype=splunk_python) (\"Failed to parse JSON\" OR \"JsonLineBreaker\" OR \"Error in 'JsonLineBreaker'\") (ai_lab OR cisco_thousandeyes_metric OR cnc_interface_counter_json) | stats count as count" \
  0

echo "All SPL checks passed."
