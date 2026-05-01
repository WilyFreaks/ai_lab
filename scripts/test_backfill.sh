#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
SPLUNK_APP="${SPLUNK_APP:-ai_lab}"
SPLUNK_AUTH="${SPLUNK_AUTH:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-${AUTH_TOKEN:-}}"
TIME_WINDOW="${TIME_WINDOW:-24h}"
SCENARIO_CONF="$ROOT_DIR/default/ai_lab_scenarios.conf"
LOCAL_SCENARIO_CONF="$ROOT_DIR/local/ai_lab_scenarios.conf"

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

run_search_csv() {
  local query="$1"
  if [[ -n "$SPLUNK_TOKEN" ]]; then
    "$SPLUNK_BIN" search "$query" -app "$SPLUNK_APP" -token "$SPLUNK_TOKEN" -earliest_time 0 -latest_time now -output csv
  else
    "$SPLUNK_BIN" search "$query" -app "$SPLUNK_APP" -auth "$SPLUNK_AUTH" -earliest_time 0 -latest_time now -output csv
  fi
}

read_backfill_window() {
  python3 - "$SCENARIO_CONF" "$LOCAL_SCENARIO_CONF" <<'PY'
import configparser
import os
import sys

default_conf, local_conf = sys.argv[1], sys.argv[2]
cfg = configparser.ConfigParser(interpolation=None, delimiters=("=",), strict=False)
if os.path.exists(default_conf):
    cfg.read(default_conf)
if os.path.exists(local_conf):
    cfg.read(local_conf)

if not cfg.has_section("baseline"):
    raise SystemExit("missing [baseline] section")

try:
    start_anchor = int(float(cfg.get("baseline", "backfill_start_time")))
except Exception:
    raise SystemExit("missing baseline.backfill_start_time")

try:
    backfill_days = int(float(cfg.get("baseline", "backfill_days")))
except Exception:
    backfill_days = 7

start_ts = start_anchor - (backfill_days * 86400)
end_ts = start_anchor
print(f"{start_ts} {end_ts}")
PY
}

read_stream_interval() {
  local stream_key="$1"
  python3 - "$SCENARIO_CONF" "$LOCAL_SCENARIO_CONF" "$stream_key" <<'PY'
import configparser
import os
import sys

default_conf, local_conf, stream_key = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = configparser.ConfigParser(interpolation=None, delimiters=("=",), strict=False)
if os.path.exists(default_conf):
    cfg.read(default_conf)
if os.path.exists(local_conf):
    cfg.read(local_conf)

interval = 1
try:
    interval = int(float(cfg.get("baseline", stream_key)))
except Exception:
    interval = 1
print(max(interval, 1))
PY
}

assert_backfill_duration_coverage() {
  local label="$1"
  local query="$2"
  local expected_start="$3"
  local expected_end="$4"
  local step_seconds="$5"
  local tmp_csv
  tmp_csv="$(mktemp)"

  if ! run_search_csv "$query" >"$tmp_csv"; then
    rm -f "$tmp_csv"
    fail "$label query failed"
  fi

  if ! python3 - "$tmp_csv" "$expected_start" "$expected_end" "$step_seconds" <<'PY'
import csv
import io
import math
import sys

csv_path, expected_start, expected_end, step_seconds = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])

raw_lines = open(csv_path, "r", encoding="utf-8").read().splitlines()
header_idx = None
for i, line in enumerate(raw_lines):
    probe = line.replace('"', "").strip().lower()
    if "min_time" in probe and "max_time" in probe and "," in probe:
        header_idx = i
        break

if header_idx is None:
    raise SystemExit("no csv payload in search output")

reader = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
rows = list(reader)
if not rows:
    raise SystemExit("no rows returned")

row = rows[0]
try:
    min_time = float(row.get("min_time", "nan"))
    max_time = float(row.get("max_time", "nan"))
except Exception:
    raise SystemExit("failed to parse min_time/max_time")

if math.isnan(min_time) or math.isnan(max_time):
    raise SystemExit("min_time/max_time missing")

# Backfill loop emits ts in range(start_ts, end_ts, step).
# So min should be close to start_ts, and max should be >= end_ts-step.
start_allow = expected_start + step_seconds
tail_target = expected_end - step_seconds

if min_time > start_allow:
    raise SystemExit(
        f"earliest event too late: min_time={min_time:.3f} expected<= {start_allow}"
    )

if max_time < tail_target:
    raise SystemExit(
        f"latest event too early: max_time={max_time:.3f} expected>= {tail_target}"
    )
PY
  then
    rm -f "$tmp_csv"
    fail "$label failed"
  fi

  rm -f "$tmp_csv"
  echo "PASS: $label"
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

assert_count_gt_zero() {
  local label="$1"
  local query="$2"
  local count

  if ! count="$(run_search "$query" | extract_count)"; then
    fail "$label query failed or did not return a numeric count"
  fi

  if (( count <= 0 )); then
    fail "$label expected > 0, got $count"
  fi

  echo "PASS: $label = $count"
}

read_bounds() {
  local selector="$1"
  local scale="$2"

  python3 - "$SCENARIO_CONF" "$selector" "$scale" <<'PY'
import re
import sys

conf_path, selector, scale = sys.argv[1], sys.argv[2], sys.argv[3]

mins = []
maxs = []
noises = []

with open(conf_path, "r", encoding="utf-8") as f:
    for raw in f:
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if selector not in key:
            continue

        try:
            v = float(value)
        except ValueError:
            continue

        if key.endswith(".daily_min"):
            mins.append(v)
        elif key.endswith(".daily_max"):
            maxs.append(v)
        elif key.endswith(".noise_stdev"):
            noises.append(v)

if not mins or not maxs:
    raise SystemExit(f"missing bounds for selector: {selector}")

min_v = min(mins)
max_v = max(maxs)
max_noise = max(noises) if noises else 0.0

# "Gradual" guardrail: a jump above either 25% of full range or 6 sigma is suspicious.
step_limit = max((max_v - min_v) * 0.25, max_noise * 6.0)

if scale == "ms_to_sec":
    min_v /= 1000.0
    max_v /= 1000.0
    step_limit /= 1000.0

print(f"{min_v} {max_v} {step_limit}")
PY
}

assert_savedsearch_time_aware_range() {
  local label="$1"
  local query="$2"
  local selector="$3"
  local mode="$4"
  local tmp_csv
  tmp_csv="$(mktemp)"

  if ! run_search_csv "$query" >"$tmp_csv"; then
    rm -f "$tmp_csv"
    fail "$label query failed"
  fi

  if ! python3 - "$SCENARIO_CONF" "$selector" "$mode" "$tmp_csv" <<'PY'
import csv
import datetime as dt
import io
import math
import re
import sys

conf_path, selector, mode, csv_path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

def weekend_multiplier(local_dt, configured):
    if configured is None:
        return 1.0
    weekday = local_dt.weekday()  # Mon=0 .. Sun=6
    hour = local_dt.hour + (local_dt.minute / 60.0)
    weekend_weight = 0.0
    if weekday == 4 and hour >= 18.0:
        weekend_weight = min(max((hour - 18.0) / 6.0, 0.0), 1.0)
    elif weekday == 5:
        weekend_weight = 1.0
    elif weekday == 6:
        if hour < 18.0:
            weekend_weight = 1.0
        else:
            weekend_weight = max(0.0, 1.0 - ((hour - 18.0) / 6.0))
    return 1.0 + ((configured - 1.0) * weekend_weight)

def parse_time(raw):
    # Example: 2026-04-26 20:00:00.000 JST
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", raw.strip())
    if not m:
        raise ValueError(f"unsupported _time format: {raw}")
    return dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")

def load_metric_params(path, selector):
    params = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("[") or "=" not in line:
                continue
            key, value = [x.strip() for x in line.split("=", 1)]
            if selector not in key:
                continue
            leaf = key.split("#")[-1]
            metric = leaf.split(".")[0]
            params.setdefault(metric, {"rates": {}})
            try:
                fv = float(value)
            except ValueError:
                continue
            if leaf.endswith(".daily_min"):
                params[metric]["daily_min"] = fv
            elif leaf.endswith(".daily_max"):
                params[metric]["daily_max"] = fv
            elif ".peak_rate_" in leaf:
                hour = int(leaf.rsplit("_", 1)[-1])
                params[metric]["rates"][hour] = fv
            elif leaf.endswith(".weekend_multiplier"):
                params[metric]["weekend_multiplier"] = fv
            elif leaf.endswith(".noise_stdev"):
                params[metric]["noise_stdev"] = fv
    return params

def metric_name_from_column(col, suffix):
    # New saved-search format (preferred): R9_HundredGigE0/0/0/29_ifOutPktsRate
    if ":" not in col:
        if col.endswith("_ifOutPktsRate"):
            return col
        if col.endswith("_ifInPktsRate"):
            return col
        return None

    # Legacy saved-search format: R9-NCS540:HundredGigE0/0/0/29
    router_part, if_part = col.split(":", 1)
    router_id = router_part.split("-", 1)[0]
    iface = if_part.replace("/", "_")
    return f"{router_id}_{iface}_{suffix}"

params = load_metric_params(conf_path, selector)
if not params:
    raise SystemExit(f"no params found for selector {selector}")

raw_lines = open(csv_path, "r", encoding="utf-8").read().splitlines()
header_idx = None
for i, line in enumerate(raw_lines):
    probe = line.replace('"', "").strip()
    if "_time" in probe and "," in probe:
        header_idx = i
        break

if header_idx is None:
    raise SystemExit("no csv payload in search output")

reader = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
violations = []
rows = 0

for row in reader:
    raw_time = row.get("_time", "")
    if not raw_time:
        continue
    try:
        local_dt = parse_time(raw_time)
    except Exception:
        continue
    rows += 1

    if mode == "interface_ifOut":
        suffix = "ifOutPktsRate"
        value_columns = [c for c in row.keys() if c and c != "_time"]
    elif mode == "interface_ifIn":
        suffix = "ifInPktsRate"
        value_columns = [c for c in row.keys() if c and c != "_time"]
    elif mode == "thousandeyes_response_sec":
        suffix = None
        value_columns = [c for c in row.keys() if c and c != "_time" and "response_time_sec" in c]
    else:
        raise SystemExit(f"unsupported mode: {mode}")

    for col in value_columns:
        raw_val = row.get(col, "")
        if raw_val in ("", None):
            continue
        try:
            value = float(raw_val)
        except ValueError:
            continue

        if mode.startswith("interface_"):
            metric = metric_name_from_column(col, suffix)
            if not metric:
                continue
            p = params.get(metric)
        else:
            metric = "response_time_ms"
            p = params.get(metric)

        if not p:
            continue
        dmin = p.get("daily_min")
        dmax = p.get("daily_max")
        rate = p.get("rates", {}).get(local_dt.hour)
        if dmin is None or dmax is None or rate is None:
            continue

        expected = dmin + (dmax - dmin) * rate
        expected *= weekend_multiplier(local_dt, p.get("weekend_multiplier"))
        noise = p.get("noise_stdev", 0.0) or 0.0
        tol = max(noise * 4.0, 1e-9)

        # thousandeyes saved search is in seconds, config is milliseconds.
        if mode == "thousandeyes_response_sec":
            expected /= 1000.0
            tol /= 1000.0

        low = expected - tol
        high = expected + tol
        if value < low or value > high:
            violations.append((raw_time, col, value, low, high))

if rows == 0:
    raise SystemExit("no rows returned")

if violations:
    sample = violations[0]
    raise SystemExit(
        f"violations={len(violations)} sample=_time:{sample[0]} metric:{sample[1]} value:{sample[2]:.6f} expected_range:[{sample[3]:.6f},{sample[4]:.6f}]"
    )
PY
  then
    rm -f "$tmp_csv"
    fail "$label failed"
  fi

  rm -f "$tmp_csv"
  echo "PASS: $label"
}

if [[ ! -x "$SPLUNK_BIN" ]]; then
  fail "Splunk CLI not found at $SPLUNK_BIN"
fi

if [[ -z "$SPLUNK_AUTH" && -z "$SPLUNK_TOKEN" ]]; then
  fail "SPLUNK_AUTH or SPLUNK_TOKEN is required"
fi

echo "Running backfill data-quality checks (app=$SPLUNK_APP, window=$TIME_WINDOW)..."

if [[ ! -f "$SCENARIO_CONF" ]]; then
  fail "Scenario config not found: $SCENARIO_CONF"
fi

read -r BACKFILL_START_TS BACKFILL_END_TS <<<"$(read_backfill_window)"
TE_INTERVAL_MIN="$(read_stream_interval "thousandeyes#cisco:thousandeyes:metric#interval")"
TM_INTERVAL_MIN="$(read_stream_interval "telemetry#cnc_interface_counter_json#interval")"
TE_STEP_SECONDS=$(( TE_INTERVAL_MIN * 60 ))
TM_STEP_SECONDS=$(( TM_INTERVAL_MIN * 60 ))

assert_backfill_duration_coverage \
  "Backfill duration coverage (thousandeyes metric head/tail)" \
  "index=thousandeyes sourcetype=cisco:thousandeyes:metric | stats min(_time) as min_time max(_time) as max_time" \
  "$BACKFILL_START_TS" \
  "$BACKFILL_END_TS" \
  "$TE_STEP_SECONDS"

assert_backfill_duration_coverage \
  "Backfill duration coverage (telemetry head/tail)" \
  "index=telemetry sourcetype=cnc_interface_counter_json | stats min(_time) as min_time max(_time) as max_time" \
  "$BACKFILL_START_TS" \
  "$BACKFILL_END_TS" \
  "$TM_STEP_SECONDS"

read -r IFOUT_MIN IFOUT_MAX IFOUT_STEP <<<"$(read_bounds "_ifOutPktsRate" "raw")"
read -r IFIN_MIN IFIN_MAX IFIN_STEP <<<"$(read_bounds "_ifInPktsRate" "raw")"
read -r TE_MIN TE_MAX TE_STEP <<<"$(read_bounds "response_time_ms" "ms_to_sec")"

assert_count_gt_zero \
  "Saved search telemetry_if_counter_test returns results" \
  "| savedsearch telemetry_if_counter_test | stats count as count"

assert_count_eq \
  "telemetry_if_counter_test has no negative directional gaps" \
  "| savedsearch telemetry_if_counter_test | search r1_to_r2_gap<0 OR r2_to_r1_gap<0 | stats count as count" \
  0

assert_count_eq \
  "telemetry_if_counter_test has no drop rate over 1%" \
  "| savedsearch telemetry_if_counter_test | search r1_to_r2_drop_rate>1 OR r2_to_r1_drop_rate>1 | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search interface_ifOutPktsRate_test returns results" \
  "| savedsearch interface_ifOutPktsRate_test | stats count as count"

assert_savedsearch_time_aware_range \
  "interface_ifOutPktsRate_test values follow day/hour config bounds" \
  "| savedsearch interface_ifOutPktsRate_test" \
  "_ifOutPktsRate" \
  "interface_ifOut"

assert_count_eq \
  "interface_ifOutPktsRate_test fluctuates gradually (no abrupt jumps)" \
  "| savedsearch interface_ifOutPktsRate_test | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$IFOUT_STEP | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search interface_ifInPktsRate_test returns results" \
  "| savedsearch interface_ifInPktsRate_test | stats count as count"

assert_savedsearch_time_aware_range \
  "interface_ifInPktsRate_test values follow day/hour config bounds" \
  "| savedsearch interface_ifInPktsRate_test" \
  "_ifInPktsRate" \
  "interface_ifIn"

assert_count_eq \
  "interface_ifInPktsRate_test fluctuates gradually (no abrupt jumps)" \
  "| savedsearch interface_ifInPktsRate_test | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$IFIN_STEP | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search thousandeyes_response_time_sec_test returns results" \
  "| savedsearch thousandeyes_response_time_sec_test | stats count as count"

assert_savedsearch_time_aware_range \
  "thousandeyes_response_time_sec_test values follow day/hour config bounds" \
  "| savedsearch thousandeyes_response_time_sec_test" \
  "response_time_ms" \
  "thousandeyes_response_sec"

assert_count_eq \
  "thousandeyes_response_time_sec_test fluctuates gradually (no abrupt jumps)" \
  "| savedsearch thousandeyes_response_time_sec_test | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$TE_STEP | stats count as count" \
  0

assert_count_eq \
  "No JSON/parser errors from ai_lab ingest paths" \
  "index=_internal earliest=-$TIME_WINDOW (sourcetype=splunkd OR sourcetype=splunk_python) (\"Failed to parse JSON\" OR \"JsonLineBreaker\" OR \"Error in 'JsonLineBreaker'\") (ai_lab OR cisco_thousandeyes_metric OR cnc_interface_counter_json) | stats count as count" \
  0

echo "Backfill SPL checks passed."
