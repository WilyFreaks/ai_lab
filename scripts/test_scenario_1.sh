#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
SPLUNK_APP="${SPLUNK_APP:-ai_lab}"
SPLUNK_AUTH="${SPLUNK_AUTH:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-${AUTH_TOKEN:-}}"

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

if [[ ! -x "$SPLUNK_BIN" ]]; then
  fail "Splunk CLI not found at $SPLUNK_BIN"
fi

if [[ -z "$SPLUNK_AUTH" && -z "$SPLUNK_TOKEN" ]]; then
  fail "SPLUNK_AUTH or SPLUNK_TOKEN is required"
fi

echo "Running scenario1 SPL checks (app=$SPLUNK_APP)..."

assert_count_eq \
  "telemetry_if_counter_test has no negative directional gaps" \
  "| savedsearch telemetry_if_counter_test | search r1_to_r2_gap<0 OR r2_to_r1_gap<0 | stats count as count" \
  0

assert_count_eq \
  "telemetry_if_counter_test has no drop rate over 1%" \
  "| savedsearch telemetry_if_counter_test | search r1_to_r2_drop_rate>1 OR r2_to_r1_drop_rate>1 | stats count as count" \
  0

echo "Scenario1 SPL checks passed."
