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

read_backfill_live_handoff_state() {
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
    print("SKIP\tmissing [baseline] section")
    raise SystemExit(0)

completed = cfg.get("baseline", "backfill_completed", fallback="false").strip().lower()
if completed != "true":
    print("SKIP\tbackfill_completed is not true")
    raise SystemExit(0)

try:
    start_anchor = int(float(cfg.get("baseline", "backfill_start_time")))
except Exception:
    print("SKIP\tmissing baseline.backfill_start_time")
    raise SystemExit(0)

first_tick = ((int(start_anchor) + 59) // 60) * 60
live_raw = cfg.get("baseline", "live_last_tick_epoch", fallback="").strip()
if not live_raw:
    print("SKIP\tlive_last_tick_epoch not set")
    raise SystemExit(0)
try:
    live_last = int(float(live_raw))
except Exception:
    print("SKIP\tlive_last_tick_epoch not parseable")
    raise SystemExit(0)

if live_last < first_tick:
    print("SKIP\tlive has not advanced through handoff tick")
    raise SystemExit(0)

print(f"RUN\t{first_tick}\t{live_last}")
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

assert_backfill_live_handoff_stream() {
  local label="$1"
  local index_sourcetype_prefix="$2"
  local first_tick="$3"
  local step_seconds="$4"
  local tmp_csv
  local slack="${BACKFILL_LIVE_HANDOFF_SLACK_SEC:-120}"
  # Max handoff gap ≲ gap_step_mult×stream step (backfill range start alignment vs end); default 2 covers one missed cadence.
  local gap_step_mult="${BACKFILL_LIVE_HANDOFF_GAP_STEP_MULT:-2}"
  tmp_csv="$(mktemp)"
  local query
  query="${index_sourcetype_prefix} earliest=0 latest=now | eval ft=${first_tick} | eval is_bf=if(_time<ft,1,0) | eval is_lv=if(_time>=ft,1,0) | stats max(eval(if(is_bf=1,_time,null()))) as last_bf min(eval(if(is_lv=1,_time,null()))) as first_lv"

  if ! run_search_csv "$query" >"$tmp_csv"; then
    rm -f "$tmp_csv"
    fail "$label query failed"
  fi

  if ! python3 - "$tmp_csv" "$first_tick" "$step_seconds" "$slack" "$gap_step_mult" <<'PY'
import csv
import io
import math
import sys

csv_path = sys.argv[1]
first_tick = int(sys.argv[2])
step_seconds = int(sys.argv[3])
slack = int(sys.argv[4])
gap_step_mult = float(sys.argv[5])

raw_lines = open(csv_path, "r", encoding="utf-8").read().splitlines()
header_idx = None
for i, line in enumerate(raw_lines):
    probe = line.replace('"', "").strip().lower()
    if "last_bf" in probe and "first_lv" in probe and "," in probe:
        header_idx = i
        break

if header_idx is None:
    raise SystemExit("no csv payload in search output")

reader = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
rows = list(reader)
if not rows:
    raise SystemExit("no rows returned")

row = rows[0]
raw_last = (row.get("last_bf") or "").strip()
raw_first = (row.get("first_lv") or "").strip()
if not raw_last or not raw_first:
    raise SystemExit(f"missing last_bf/first_lv (last_bf={raw_last!r} first_lv={raw_first!r})")

try:
    last_bf = float(raw_last)
    first_lv = float(raw_first)
except Exception as e:
    raise SystemExit(f"parse last_bf/first_lv: {e}") from e

if math.isnan(last_bf) or math.isnan(first_lv):
    raise SystemExit("last_bf/first_lv not numeric")

# Generators: last backfill tick ~= first_tick - step; first live tick ~= first_tick.
if last_bf < first_tick - step_seconds - slack:
    raise SystemExit(
        f"backfill tail too early: last_bf={last_bf:.3f} expected>= {first_tick - step_seconds - slack} "
        f"(first_tick={first_tick} step={step_seconds} slack={slack})"
    )

if first_lv < first_tick - slack:
    raise SystemExit(
        f"first live event too early: first_lv={first_lv:.3f} expected>= {first_tick - slack}"
    )

if first_lv > first_tick + slack:
    raise SystemExit(
        f"first live event too late: first_lv={first_lv:.3f} expected<= {first_tick + slack}"
    )

gap = first_lv - last_bf
if gap < 0:
    raise SystemExit(f"live before last backfill event: gap={gap:.3f}")

max_gap = gap_step_mult * step_seconds + slack
if gap > max_gap:
    raise SystemExit(
        f"handoff gap too large (missing/near-boundary stall): gap={gap:.3f}s max≈{max_gap:.1f}s "
        f"(step={step_seconds} mult={gap_step_mult} slack={slack}) "
        f"last_bf={last_bf:.3f} first_lv={first_lv:.3f} first_tick={first_tick}"
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

assert_count_range() {
  local label="$1"
  local query="$2"
  local min_expected="$3"
  local max_expected="$4"
  local count

  if ! count="$(run_search "$query" | extract_count)"; then
    fail "$label query failed or did not return a numeric count"
  fi

  if (( count < min_expected || count > max_expected )); then
    fail "$label expected between $min_expected and $max_expected, got $count"
  fi

  echo "PASS: $label = $count (allowed range: $min_expected-$max_expected)"
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

  if ! python3 - "$SCENARIO_CONF" "$LOCAL_SCENARIO_CONF" "$selector" "$mode" "$tmp_csv" <<'PY'
import csv
import datetime as dt
import io
import math
import os
import re
import sys

default_conf, local_conf, selector, mode, csv_path = (
    sys.argv[1],
    sys.argv[2],
    sys.argv[3],
    sys.argv[4],
    sys.argv[5],
)

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

def merged_baseline_key_values(default_path, local_path):
    """Splunk-merge order: default then local overrides (same stanza semantics)."""
    merged = {}
    for path in (default_path, local_path):
        if not path or not os.path.isfile(path):
            continue
        section = None
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().lower()
                    continue
                if section != "baseline" or "=" not in line:
                    continue
                key, value = [x.strip() for x in line.split("=", 1)]
                merged[key] = value
    return merged


def trend_anchor_epoch(baseline_kv):
    head = baseline_kv.get("backfill_head_time")
    if head is not None:
        head = head.strip()
        if head != "":
            try:
                return float(head)
            except ValueError:
                pass
    anchor_raw = baseline_kv.get("backfill_start_time")
    if not anchor_raw:
        return None
    try:
        anchor_epoch = float(anchor_raw.strip())
    except ValueError:
        return None
    try:
        days = int(float(baseline_kv.get("backfill_days", "7")))
    except ValueError:
        days = 7
    days = days or 7
    return anchor_epoch - (days * 86400.0)


def load_metric_params(baseline_kv, selector):
    params = {}
    for key, value in baseline_kv.items():
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
        elif leaf.endswith(".daily_variation_stdev"):
            params[metric]["daily_variation_stdev"] = fv
        elif leaf.endswith(".trend_per_day"):
            params[metric]["trend_per_day"] = fv
    return params

def interpolated_rate(local_dt, rates):
    current_hour = local_dt.hour
    next_hour = (current_hour + 1) % 24
    current_rate = rates.get(current_hour)
    if current_rate is None:
        return None
    next_rate = rates.get(next_hour, current_rate)
    minute_progress = (local_dt.minute + (local_dt.second / 60.0)) / 60.0
    return current_rate + ((next_rate - current_rate) * minute_progress)

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

baseline_kv = merged_baseline_key_values(default_conf, local_conf)
params = load_metric_params(baseline_kv, selector)
trend_zero = trend_anchor_epoch(baseline_kv)
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
        rate = interpolated_rate(local_dt, p.get("rates", {}))
        if dmin is None or dmax is None or rate is None:
            continue

        expected = dmin + (dmax - dmin) * rate
        expected *= weekend_multiplier(local_dt, p.get("weekend_multiplier"))
        t_day = float(p.get("trend_per_day") or 0.0)
        if trend_zero is not None and t_day != 0.0:
            days_elapsed = max(0.0, (local_dt.timestamp() - trend_zero) / 86400.0)
            tm = max(0.05, min(10.0, 1.0 + t_day * days_elapsed))
            expected *= tm
        noise = p.get("noise_stdev", 0.0) or 0.0
        dvar_stdev = p.get("daily_variation_stdev", 0.0) or 0.0
        # Tolerance covers per-event noise (4σ) plus daily-variation shift (3σ of
        # the multiplicative factor applied to the expected value).
        tol = max(noise * 4.0, expected * dvar_stdev * 3.0, 1e-9)

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

assert_twamp_minute_bucket_count() {
  local label="$1"
  local min_ok="${TWAMP_MINUTE_BUCKET_MIN:-3}"
  local max_ok="${TWAMP_MINUTE_BUCKET_MAX:-6}"
  local tmp_csv
  tmp_csv="$(mktemp)"

  if ! run_search_csv "| savedsearch twamp_event_count" >"$tmp_csv"; then
    rm -f "$tmp_csv"
    fail "$label query failed"
  fi

  if ! python3 - "$tmp_csv" "$min_ok" "$max_ok" <<'PY'
import csv
import io
import sys

csv_path, min_ok, max_ok = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
raw_lines = open(csv_path, "r", encoding="utf-8").read().splitlines()
header_idx = None
for i, line in enumerate(raw_lines):
    stripped = line.strip()
    if not stripped:
        continue
    if stripped.startswith("WARNING:") or stripped.startswith("INFO:"):
        continue
    probe = line.replace('"', "").strip().lower()
    if "," not in probe:
        continue
    if "minute_buckets" in probe:
        header_idx = i
        break
    if "event_count" in probe:
        header_idx = i
        break
    if "_time" in probe:
        header_idx = i
        break
    if "session name" in probe:
        header_idx = i
        break

if header_idx is None:
    raise SystemExit("no csv header row for twamp_event_count")

reader = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
rows = list(reader)
if not rows:
    raise SystemExit("no rows from twamp_event_count")

row = rows[0]
val = None
for key in (
    "minute_buckets_with_data",
    "minute_buckets",
    "event_count",
    "count",
):
    if key in row and row[key] not in (None, ""):
        val = int(float(row[key]))
        break
if val is None:
    # Fallback for pivoted chart output (e.g. count by _time "Session Name"):
    # each non-_time column is a per-session count (often ~5 in a 5m window).
    candidates = []
    for r in rows:
        for k, v in r.items():
            if v in (None, ""):
                continue
            kl = (k or "").strip().lower()
            if kl in ("_time", "time", "preview"):
                continue
            try:
                candidates.append(int(float(v)))
            except ValueError:
                continue
    if candidates:
        val = max(candidates)

if val is None:
    raise SystemExit(f"could not parse minute bucket count from row={row}")

if val < min_ok or val > max_ok:
    raise SystemExit(
        f"minute_buckets_with_data={val} expected between {min_ok} and {max_ok} (5m window, partial edges OK)"
    )
PY
  then
    rm -f "$tmp_csv"
    fail "$label failed"
  fi

  rm -f "$tmp_csv"
  echo "PASS: $label"
}

assert_twamp_directional_avg_metric() {
  local label="$1"
  local savedsearch="$2"
  local metric_leaf="$3"
  local value_column="$4"
  local tmp_csv
  tmp_csv="$(mktemp)"

  if ! run_search_csv "| savedsearch $savedsearch" >"$tmp_csv"; then
    rm -f "$tmp_csv"
    fail "$label query failed"
  fi

  if ! python3 - "$SCENARIO_CONF" "$tmp_csv" "$metric_leaf" "$value_column" <<'PY'
import csv
import io
import re
import sys

conf_path, csv_path, metric_leaf, value_column = sys.argv[1:5]

def parse_default_noise(path):
    key = "twamp#pca_twamp_csv#sample.csv#default.noise_stdev"
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                tokens = v.strip().split()
                if not tokens:
                    return 0.0
                try:
                    return float(tokens[0])
                except ValueError:
                    return 0.0
    return 0.0

def aggregate_bounds(path, direction):
    pat = re.compile(
        rf"^twamp#pca_twamp_csv#sample\.csv#slice\d+_{direction}_{re.escape(metric_leaf)}\.daily_(min|max)$"
    )
    mins = []
    maxs = []
    specific_noise = []
    noise_key_end = f"_{direction}_{metric_leaf}.noise_stdev"
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            tokens = v.strip().split()
            if not tokens:
                continue
            v = tokens[0]
            m = pat.match(k)
            if m:
                side = m.group(1)
                try:
                    fv = float(v)
                except ValueError:
                    continue
                if side == "min":
                    mins.append(fv)
                else:
                    maxs.append(fv)
            if k.endswith(noise_key_end):
                try:
                    specific_noise.append(float(v))
                except ValueError:
                    pass
    if not mins or not maxs:
        raise SystemExit(f"missing twamp {metric_leaf} bounds for direction={direction}")
    lo, hi = min(mins), max(maxs)
    dn = parse_default_noise(path)
    noise = max(specific_noise) if specific_noise else dn
    tol = max(noise * 4.0, 1e-6)
    return lo - tol, hi + tol

bounds = {
    "ul": aggregate_bounds(conf_path, "ul"),
    "dl": aggregate_bounds(conf_path, "dl"),
    "rt": aggregate_bounds(conf_path, "rt"),
}

raw_lines = open(csv_path, "r", encoding="utf-8").read().splitlines()
header_idx = None
for i, line in enumerate(raw_lines):
    probe = line.replace('"', "").strip()
    lower = probe.lower()
    if "," not in lower:
        continue
    # Legacy directional header.
    if "direction" in lower and value_column in lower:
        header_idx = i
        break
    # Current wide chart header (_time + avg(<dir>_<metric>): <session>...).
    if "_time" in lower and f"avg(ul_{metric_leaf})" in lower:
        header_idx = i
        break

if header_idx is None:
    for i, line in enumerate(raw_lines):
        lower = line.replace('"', "").strip().lower()
        if "," not in lower:
            continue
        if "direction" in lower or "_time" in lower:
            header_idx = i
            break

if header_idx is None:
    raise SystemExit("no csv header for twamp directional avg search")

reader = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
rows = list(reader)
if not rows:
    raise SystemExit("no rows returned from twamp saved search")

violations = []
seen_dirs = set()

# Legacy output shape:
# direction,avg_dmean
# ul,27.2
# dl,22.4
# rt,50.8
if "direction" in (reader.fieldnames or []) and value_column in (reader.fieldnames or []):
    directional_rows = [r for r in rows if r.get("direction")]
    if len(directional_rows) < 3:
        raise SystemExit(f"expected 3 direction rows, got {len(directional_rows)}")

    for row in directional_rows:
        d = str(row.get("direction", "")).strip().lower()
        raw = row.get(value_column, "")
        if not d or raw in (None, ""):
            continue
        seen_dirs.add(d)
        try:
            val = float(raw)
        except ValueError:
            violations.append((d, raw, "non-numeric"))
            continue
        if d not in bounds:
            continue
        lo, hi = bounds[d]
        if val < lo or val > hi:
            violations.append((d, val, f"outside [{lo:.6f},{hi:.6f}]"))
else:
    # Current wide chart shape:
    # _time,avg(dl_dmean): <session>,avg(rt_dmean): <session>,avg(ul_dmean): <session>,...
    fieldnames = reader.fieldnames or []
    col_dir = {}
    for col in fieldnames:
        if not col:
            continue
        normalized = col.replace('"', "").strip().lower()
        match = re.match(rf"^avg\((ul|dl|rt)_{re.escape(metric_leaf)}\)\s*:", normalized)
        if match:
            col_dir[col] = match.group(1)

    if not col_dir:
        raise SystemExit("no directional avg columns found in twamp saved search output")

    for row in rows:
        for col, d in col_dir.items():
            raw = row.get(col, "")
            if raw in (None, ""):
                continue
            seen_dirs.add(d)
            try:
                val = float(raw)
            except ValueError:
                violations.append((d, raw, "non-numeric"))
                continue
            lo, hi = bounds[d]
            if val < lo or val > hi:
                violations.append((d, val, f"outside [{lo:.6f},{hi:.6f}]"))

if violations:
    v = violations[0]
    raise SystemExit(f"twamp {metric_leaf} violations={len(violations)} sample={v}")

for d in ("ul", "dl", "rt"):
    if d not in seen_dirs:
        raise SystemExit(f"missing direction {d} in saved search output")
PY
  then
    rm -f "$tmp_csv"
    fail "$label failed"
  fi

  rm -f "$tmp_csv"
  echo "PASS: $label"
}

assert_thousandeyes_trend_per_day() {
  local label="$1"
  # Compares median response_time_sec in two narrow Splunk windows (Wed 14:05 local).
  # TREND_SAMPLE_WINDOW_HALF_SEC (default 420) widens ± event capture.
  # TREND_PER_DAY_ASSERTION_TOL (default 0.20) fractional slack vs expected multiplier ratio.
  local cfg_line early late per_day
  local csv_e csv_l

  if ! cfg_line="$(
    python3 - "$SCENARIO_CONF" "$LOCAL_SCENARIO_CONF" "$BACKFILL_START_TS" "$BACKFILL_END_TS" <<'PY'
import os
import sys
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

default_conf, local_conf, head_ts_s, tail_ts_s = sys.argv[1:]
head_ts = int(head_ts_s)
tail_ts = int(tail_ts_s)

REGION_TZ = {"au": "Australia/Sydney", "jp": "Asia/Tokyo"}


def merged_baseline_key_values(default_path, local_path):
    merged = {}
    for path in (default_path, local_path):
        if not path or not os.path.isfile(path):
            continue
        section = None
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1].strip().lower()
                    continue
                if section != "baseline" or "=" not in line:
                    continue
                k, v = [x.strip() for x in line.split("=", 1)]
                merged[k] = v
    return merged


baseline_kv = merged_baseline_key_values(default_conf, local_conf)

per_day_val = None
for k, v in baseline_kv.items():
    if "response_time_ms" not in k or not k.endswith(".trend_per_day"):
        continue
    try:
        per_day_val = float(v)
    except ValueError:
        continue
    break

if per_day_val is None or abs(per_day_val) < 1e-9:
    print("SKIP", "no nonzero response_time_ms.trend_per_day in baseline", flush=True)
    raise SystemExit(0)

head_raw = baseline_kv.get("backfill_head_time", "").strip()
if head_raw != "":
    try:
        trend_zero = float(head_raw)
    except ValueError:
        trend_zero = None
else:
    trend_zero = None
if trend_zero is None:
    try:
        anchor = float(baseline_kv.get("backfill_start_time", "nan"))
    except ValueError:
        anchor = None
    if anchor is None:
        print("SKIP", "missing baseline.backfill_start_time for trend anchor", flush=True)
        raise SystemExit(0)
    try:
        days = int(float(baseline_kv.get("backfill_days", "7")))
    except ValueError:
        days = 7
    if days < 1:
        days = 7
    trend_zero = anchor - (days * 86400.0)

region = (baseline_kv.get("region", "") or "").strip().lower()
tz_name = REGION_TZ.get(region)
if not tz_name:
    print("SKIP", f"unsupported or missing baseline.region={region!r}", flush=True)
    raise SystemExit(0)


def slot_epoch_after(tzname, min_epoch, dow_py, hh, mm):
    tz = ZoneInfo(tzname)
    dt0 = datetime.fromtimestamp(min_epoch, tz=tz).date()
    for off in range(400):
        d = dt0 + timedelta(days=off)
        if d.weekday() != dow_py:
            continue
        cand = datetime.combine(d, dtime(hour=hh, minute=mm), tzinfo=tz)
        te = cand.timestamp()
        if te >= min_epoch:
            return int(te)
    return None


def slot_epoch_before(tzname, max_epoch, dow_py, hh, mm):
    tz = ZoneInfo(tzname)
    dt0 = datetime.fromtimestamp(max_epoch, tz=tz).date()
    for off in range(400):
        d = dt0 - timedelta(days=off)
        if d.weekday() != dow_py:
            continue
        cand = datetime.combine(d, dtime(hour=hh, minute=mm), tzinfo=tz)
        te = cand.timestamp()
        if te <= max_epoch:
            return int(te)
    return None


# Avoid midnight daily-variation blend and weekend ramp edges: weekday @ 14:05 local.
EDGE_SKIP = int(86400 * 2.5)
DOW_PY = 2  # Wednesday
HH, MM = 14, 5

early = slot_epoch_after(tz_name, head_ts + EDGE_SKIP, DOW_PY, HH, MM)
late = slot_epoch_before(tz_name, tail_ts - EDGE_SKIP, DOW_PY, HH, MM)
if early is None or late is None:
    print("SKIP", "could not locate Wednesday 14:05 slots inside backfill span", flush=True)
    raise SystemExit(0)
if late <= early + 7 * 86400:
    print("SKIP", "backfill span too short for two separated Wednesday slots", flush=True)
    raise SystemExit(0)

de = max(0.0, (early - trend_zero) / 86400.0)
dl = max(0.0, (late - trend_zero) / 86400.0)
exp_ratio = (1.0 + per_day_val * dl) / max(1e-12, (1.0 + per_day_val * de))

try:
    tol = float(os.environ.get("TREND_PER_DAY_ASSERTION_TOL", "0.20").strip().split()[0].replace(",", "."))
except ValueError:
    tol = 0.20

print(
    f"RUN\t{early}\t{late}\t{per_day_val}\t{trend_zero}\t{exp_ratio:.8f}\t{de:.6f}\t{dl:.6f}\t{tol}",
    flush=True,
)
PY
  )"; then
    fail "$label plan script failed"
  fi

  if [[ "$(echo "$cfg_line" | head -1)" == SKIP\ * ]]; then
    echo "PASS: $label ($(echo "$cfg_line" | head -1))"
    return
  fi
  local run_line tag
  run_line="$(echo "$cfg_line" | grep '^RUN' || true)"
  if [[ -z "$run_line" ]]; then
    fail "$label expected RUN plan line from python"
  fi
  IFS=$'\t' read -r tag early late per_day trend_zero exp_ratio_raw de_raw dl_raw tol_raw <<<"$run_line"
  if [[ "$tag" != "RUN" ]]; then
    fail "$label unexpected plan line (expected RUN): $run_line"
  fi

  csv_e="$(mktemp)"
  csv_l="$(mktemp)"
  trap 'rm -f "$csv_e" "$csv_l"' RETURN

  win_half="${TREND_SAMPLE_WINDOW_HALF_SEC:-420}"
  if ! run_search_csv \
    "index=thousandeyes sourcetype=cisco:thousandeyes:metric earliest=$((early - win_half)) latest=$((early + win_half)) | fields _time response_time_sec | search response_time_sec>0 response_time_sec<10" \
    >"$csv_e"; then
    rm -f "$csv_e" "$csv_l"
    fail "$label early-slot Splunk query failed"
  fi
  if ! run_search_csv \
    "index=thousandeyes sourcetype=cisco:thousandeyes:metric earliest=$((late - win_half)) latest=$((late + win_half)) | fields _time response_time_sec | search response_time_sec>0 response_time_sec<10" \
    >"$csv_l"; then
    rm -f "$csv_e" "$csv_l"
    fail "$label late-slot Splunk query failed"
  fi

  set +e
  eval_out="$(python3 - "$csv_e" "$csv_l" "$per_day" "$exp_ratio_raw" "$de_raw" "$dl_raw" "$tol_raw" <<'PY'
import csv
import io
import statistics
import sys


def load_vals(path):
    raw_lines = open(path, encoding="utf-8").read().splitlines()
    header_idx = None
    for i, line in enumerate(raw_lines):
        lower = line.replace('"', "").strip().lower()
        if "response_time_sec" in lower and "," in lower:
            header_idx = i
            break
    if header_idx is None:
        return []
    rows = csv.DictReader(io.StringIO("\n".join(raw_lines[header_idx:])))
    out = []
    for row in rows:
        raw = row.get("response_time_sec", "").strip('"')
        if raw in ("", None):
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        if 0 < v < 10:
            out.append(v)
    return out


ep, lp, per_day_f, exp_ratio_s, de_s, dl_s, tol_s = sys.argv[1:]
per_day_f = float(per_day_f)
exp_expected = float(exp_ratio_s)
de = float(de_s)
dl = float(dl_s)
tol_frac = float(tol_s)

vals_e = load_vals(ep)
vals_l = load_vals(lp)
if len(vals_e) < 3 or len(vals_l) < 3:
    print("INSUFFICIENT\t%d\t%d" % (len(vals_e), len(vals_l)))
    sys.exit(2)

med_e = statistics.median(vals_e)
med_l = statistics.median(vals_l)
if med_e <= 1e-9:
    print("BAD_MEDIAN")
    sys.exit(2)

obs = med_l / med_e
slack = tol_frac + 0.10 * abs(dl - de)
lo = exp_expected * (1.0 - slack)
hi = exp_expected * (1.0 + slack)
if obs < lo or obs > hi:
    sys.stderr.write(
        "ratio obs=%.6f exp=%.6f range=[%.6f,%.6f] med_early=%.6f med_late=%.6f n=%d/%d\n"
        % (obs, exp_expected, lo, hi, med_e, med_l, len(vals_e), len(vals_l))
    )
    sys.exit(1)

sys.stderr.write("OK obs=%.6f expected_ratio=%.6f med_early=%.6f med_late=%.6f\n" % (obs, exp_expected, med_e, med_l))
sys.exit(0)
PY
  2>&1)"
  eval_st=$?
  set -e

  if [[ "$eval_st" -eq 2 ]]; then
    echo "PASS: $label (skipped: insufficient raw samples $(echo "$eval_out" | tr '\n' ' '))"
    return
  fi
  if [[ "$eval_st" -ne 0 ]]; then
    eval_msg="$(echo "$eval_out" | tr '\n' ' ')"
    fail "$label median ratio vs trend_per_day failed (${eval_msg})"
  fi

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
TE_INTERVAL_MIN="$(read_stream_interval "thousandeyes#cisco:thousandeyes:metric#sample.json#interval")"
TM_INTERVAL_MIN="$(read_stream_interval "telemetry#cnc_interface_counter_json#sample.json#interval")"
TE_JUMP_OUTLIER_MIN="${TE_JUMP_OUTLIER_MIN:-0}"
# Default ceiling scales with backfill_days: each outlier event creates 2 jumps (spike + return),
# outlier_probability=0.0001 over 1440 min/day × backfill_days; allow 4× Poisson headroom.
_TE_BACKFILL_DAYS="$(python3 -c "
import re
days = 7
for line in open('$SCENARIO_CONF'):
    m = re.match(r'^\s*backfill_days\s*=\s*(\d+)', line)
    if m:
        days = int(m.group(1))
print(days)
" 2>/dev/null || echo 7)"
_TE_OUTLIER_MAX_AUTO=$(( _TE_BACKFILL_DAYS * 1440 / 10000 * 2 * 4 ))
_TE_OUTLIER_MAX_AUTO=$(( _TE_OUTLIER_MAX_AUTO < 4 ? 4 : _TE_OUTLIER_MAX_AUTO ))
TE_JUMP_OUTLIER_MAX="${TE_JUMP_OUTLIER_MAX:-$_TE_OUTLIER_MAX_AUTO}"
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

HANDOFF_LINE="$(read_backfill_live_handoff_state)"
if [[ "$HANDOFF_LINE" == SKIP$'\t'* ]]; then
  _handoff_reason="${HANDOFF_LINE#*$'\t'}"
  echo "PASS: Backfill/live handoff continuity (skipped: ${_handoff_reason})"
else
  IFS=$'\t' read -r _handoff_mode HANDOFF_FIRST_TICK _ <<<"$HANDOFF_LINE"
  if [[ "$_handoff_mode" != RUN ]] || [[ -z "${HANDOFF_FIRST_TICK:-}" ]]; then
    fail "Backfill/live handoff: unexpected state line: $HANDOFF_LINE"
  fi
  assert_backfill_live_handoff_stream \
    "Backfill/live handoff (thousandeyes)" \
    "index=thousandeyes sourcetype=cisco:thousandeyes:metric" \
    "$HANDOFF_FIRST_TICK" \
    "$TE_STEP_SECONDS"
  assert_backfill_live_handoff_stream \
    "Backfill/live handoff (telemetry cnc_interface_counter_json)" \
    "index=telemetry sourcetype=cnc_interface_counter_json" \
    "$HANDOFF_FIRST_TICK" \
    "$TM_STEP_SECONDS"
fi

read -r IFOUT_MIN IFOUT_MAX IFOUT_STEP <<<"$(read_bounds "_ifOutPktsRate" "raw")"
read -r IFIN_MIN IFIN_MAX IFIN_STEP <<<"$(read_bounds "_ifInPktsRate" "raw")"
read -r TE_MIN TE_MAX TE_STEP <<<"$(read_bounds "response_time_ms" "ms_to_sec")"

assert_count_gt_zero \
  "Saved search telemetry_if_counter returns results" \
  "| savedsearch telemetry_if_counter | stats count as count"

assert_count_eq \
  "telemetry_if_counter has no negative directional gaps" \
  "| savedsearch telemetry_if_counter | search r1_to_r2_gap<0 OR r2_to_r1_gap<0 | stats count as count" \
  0

assert_count_eq \
  "telemetry_if_counter has no drop rate over 1%" \
  "| savedsearch telemetry_if_counter | search r1_to_r2_drop_rate>1 OR r2_to_r1_drop_rate>1 | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search cnc_interface_ifOutPktsRate returns results" \
  "| savedsearch cnc_interface_ifOutPktsRate | stats count as count"

assert_savedsearch_time_aware_range \
  "cnc_interface_ifOutPktsRate values follow day/hour config bounds" \
  "| savedsearch cnc_interface_ifOutPktsRate" \
  "_ifOutPktsRate" \
  "interface_ifOut"

assert_count_eq \
  "cnc_interface_ifOutPktsRate fluctuates gradually (no abrupt jumps)" \
  "| savedsearch cnc_interface_ifOutPktsRate | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$IFOUT_STEP | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search cnc_interface_ifInPktsRate returns results" \
  "| savedsearch cnc_interface_ifInPktsRate | stats count as count"

assert_savedsearch_time_aware_range \
  "cnc_interface_ifInPktsRate values follow day/hour config bounds" \
  "| savedsearch cnc_interface_ifInPktsRate" \
  "_ifInPktsRate" \
  "interface_ifIn"

assert_count_eq \
  "cnc_interface_ifInPktsRate fluctuates gradually (no abrupt jumps)" \
  "| savedsearch cnc_interface_ifInPktsRate | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$IFIN_STEP | stats count as count" \
  0

assert_count_gt_zero \
  "Saved search thousandeyes_response_time_sec returns results" \
  "| savedsearch thousandeyes_response_time_sec | stats count as count"

assert_count_gt_zero \
  "Saved search cnc_srte_path returns results" \
  "| savedsearch cnc_srte_path | stats count as count"

assert_count_gt_zero \
  "Saved search cnc_service_health returns results" \
  "| savedsearch cnc_service_health | stats count as count"

assert_count_eq \
  "cnc_service_health baseline has no SERVICE_DEGRADED rows" \
  "| savedsearch cnc_service_health | search generated_data=\"*SERVICE_DEGRADED*\" | stats count as count" \
  0

assert_twamp_minute_bucket_count \
  "twamp_event_count minute buckets in 5m window (expect ~5; edges may be lower)"

assert_twamp_directional_avg_metric \
  "twamp_dmean averages within configured daily_min/daily_max per direction" \
  "twamp_dmean" \
  "dmean" \
  "avg_dmean"

assert_twamp_directional_avg_metric \
  "twamp_jmean averages within configured daily_min/daily_max per direction" \
  "twamp_jmean" \
  "jmean" \
  "avg_jmean"

assert_savedsearch_time_aware_range \
  "thousandeyes_response_time_sec values follow day/hour config bounds" \
  "| savedsearch thousandeyes_response_time_sec" \
  "response_time_ms" \
  "thousandeyes_response_sec"

assert_count_range \
  "thousandeyes_response_time_sec fluctuates gradually (abrupt jumps within expected outlier range)" \
  "| savedsearch thousandeyes_response_time_sec | untable _time metric value | sort 0 metric _time | streamstats current=f last(value) as prev by metric | eval delta=abs(value-prev) | where isnum(prev) AND delta>$TE_STEP | stats count as count" \
  "$TE_JUMP_OUTLIER_MIN" \
  "$TE_JUMP_OUTLIER_MAX"

assert_thousandeyes_trend_per_day \
  "ThousandEyes raw response_time_sec median ratio matches trend_per_day vs backfill head (Wed 14:05 slots)"

assert_count_eq \
  "No JSON/parser errors from ai_lab ingest paths" \
  "index=_internal earliest=-$TIME_WINDOW (sourcetype=splunkd OR sourcetype=splunk_python) (\"Failed to parse JSON\" OR \"JsonLineBreaker\" OR \"Error in 'JsonLineBreaker'\") (ai_lab OR cisco_thousandeyes_metric OR cnc_interface_counter_json) | stats count as count" \
  0

echo "Backfill SPL checks passed."
