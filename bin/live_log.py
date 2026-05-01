import csv
import json
import os
import random
import re
import time
from configparser import ConfigParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
SAMPLES_DIR = os.path.join(APP_ROOT, "samples")
SPOOL_ROOT = os.path.join(APP_ROOT, "var", "spool", "ai_lab")
GEN_LOG_DIR = os.path.join(SPOOL_ROOT, "ai_lab_log", "log_generation")
LOOKUPS_DIR = os.path.join(APP_ROOT, "lookups")

PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

REGION_TZ = {
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
}

LIVE_CURSOR_KEY = "live_last_tick_epoch"

STREAMS = [
    {
        "index": "thousandeyes",
        "sourcetype": "cisco:thousandeyes:metric",
        "sample": os.path.join(
            SAMPLES_DIR, "thousandeyes", "cisco:thousandeyes:metric", "sample.json"
        ),
        "spool_dir": os.path.join(
            SPOOL_ROOT, "thousandeyes", "cisco_thousandeyes_metric"
        ),
    },
    {
        "index": "telemetry",
        "sourcetype": "cnc_interface_counter_json",
        "sample": os.path.join(
            SAMPLES_DIR, "telemetry", "cnc_interface_counter_json", "sample.json"
        ),
        "spool_dir": os.path.join(
            SPOOL_ROOT, "telemetry", "cnc_interface_counter_json"
        ),
    },
]


def telemetry_link_lookup_path():
    preferred = os.path.join(LOOKUPS_DIR, "router_if_connected_bidirectional.csv")
    if os.path.exists(preferred):
        return preferred
    return os.path.join(LOOKUPS_DIR, "router_if_connections_bidirectional.csv")


def load_telemetry_bidirectional_links():
    path = telemetry_link_lookup_path()
    if not os.path.exists(path):
        return []

    links = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r1 = str(row.get("router1", "")).strip()
            i1 = str(row.get("interface1", "")).strip()
            r2 = str(row.get("router2", "")).strip()
            i2 = str(row.get("interface2", "")).strip()
            if not (r1 and i1 and r2 and i2):
                continue
            links.append((r1, i1, r2, i2))
    return links


def telemetry_key(router_id, interface_name, direction):
    return (str(router_id).strip(), str(interface_name).strip(), str(direction).strip())


def index_telemetry_placeholders(placeholders):
    idx = {}
    for ph in placeholders:
        m = re.match(r"^(R\d+)_(.+)_(ifInPktsRate|ifOutPktsRate)$", ph)
        if not m:
            continue
        router_id = m.group(1)
        iface_token = m.group(2)
        direction = m.group(3)
        iface_name = iface_token
        if iface_name.startswith("Bundle_Ether"):
            iface_name = iface_name.replace("Bundle_Ether", "Bundle-Ether", 1)
        iface_name = iface_name.replace("_", "/")
        idx[telemetry_key(router_id, iface_name, direction)] = ph
    return idx


def enforce_telemetry_directional_conservation(replacements, placeholder_index, links):
    def _bounded_inbound(out_val, in_val):
        if out_val <= 0:
            return out_val
        lower = out_val * 0.99
        if in_val > out_val:
            return out_val
        if in_val < lower:
            return lower
        return in_val

    for (r1, i1, r2, i2) in links:
        key_out_1 = telemetry_key(r1, i1, "ifOutPktsRate")
        key_in_2 = telemetry_key(r2, i2, "ifInPktsRate")
        ph_out_1 = placeholder_index.get(key_out_1)
        ph_in_2 = placeholder_index.get(key_in_2)
        if ph_out_1 and ph_in_2:
            out1 = float(replacements.get(ph_out_1, 0) or 0)
            in2 = float(replacements.get(ph_in_2, 0) or 0)
            replacements[ph_in_2] = round(_bounded_inbound(out1, in2), 6)

        key_out_2 = telemetry_key(r2, i2, "ifOutPktsRate")
        key_in_1 = telemetry_key(r1, i1, "ifInPktsRate")
        ph_out_2 = placeholder_index.get(key_out_2)
        ph_in_1 = placeholder_index.get(key_in_1)
        if ph_out_2 and ph_in_1:
            out2 = float(replacements.get(ph_out_2, 0) or 0)
            in1 = float(replacements.get(ph_in_1, 0) or 0)
            replacements[ph_in_1] = round(_bounded_inbound(out2, in1), 6)


def _new_cfg():
    return ConfigParser(interpolation=None, delimiters=("=",), strict=False)


def read_effective_conf():
    cfg = _new_cfg()
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def read_local_conf():
    cfg = _new_cfg()
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def write_local_conf(cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        cfg.write(f)


def write_generation_log(event, **fields):
    os.makedirs(GEN_LOG_DIR, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "live_log",
        "event": event,
    }
    payload.update(fields)
    path = os.path.join(
        GEN_LOG_DIR, f"log_generation_{int(time.time() * 1_000_000)}_{os.getpid()}.json"
    )
    with open(path, "w") as f:
        f.write(json.dumps(payload, separators=(",", ":")))
        f.write("\n")


def get_region_tz(cfg):
    region = cfg.get("baseline", "region", fallback="").strip().lower()
    tz_name = REGION_TZ.get(region, "UTC")
    return ZoneInfo(tz_name), region or "unknown"


def format_domain_timestamp(local_dt, region):
    wall = local_dt.strftime("%Y-%m-%dT%H:%M:%S")
    if region == "jp":
        return f"{wall} JST"
    if region == "au":
        abbr = local_dt.tzname() or ""
        if abbr:
            return f"{wall} {abbr}"
        return f"{wall} AEST"
    tzabbr = (local_dt.tzname() or "UTC").strip()
    return f"{wall} {tzabbr}"


def parse_float(cfg, section, key, default=None):
    try:
        return float(cfg.get(section, key))
    except Exception:
        return default


def parse_int(cfg, section, key, default=None):
    try:
        return int(float(cfg.get(section, key)))
    except Exception:
        return default


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


def metric_value(cfg, section, prefix, local_dt):
    base = parse_float(cfg, section, prefix, default=None)
    if base is None:
        return None

    dmin = parse_float(cfg, section, f"{prefix}.daily_min", default=None)
    dmax = parse_float(cfg, section, f"{prefix}.daily_max", default=None)
    rate = parse_float(cfg, section, f"{prefix}.peak_rate_{local_dt.hour:02d}", default=None)

    if dmin is not None and dmax is not None and rate is not None:
        value = dmin + (dmax - dmin) * rate
    else:
        value = base

    wmul = parse_float(cfg, section, f"{prefix}.weekend_multiplier", default=None)
    value *= weekend_multiplier(local_dt, wmul)

    outlier_p = parse_float(cfg, section, f"{prefix}.outlier_probability", default=0.0) or 0.0
    if outlier_p > 0 and random.random() < outlier_p:
        omin = parse_float(cfg, section, f"{prefix}.outlier_min", default=value)
        omax = parse_float(cfg, section, f"{prefix}.outlier_max", default=value)
        if omin is not None and omax is not None:
            value = random.uniform(min(omin, omax), max(omin, omax))

    noise = parse_float(cfg, section, f"{prefix}.noise_stdev", default=0.0) or 0.0
    if noise > 0:
        value += random.gauss(0.0, noise)

    return value


def coerce_placeholder(cfg, section, prefix, placeholder, local_dt, sequence, stream, region):
    if placeholder == "timestamp":
        return format_domain_timestamp(local_dt, region)
    if placeholder == "sequence":
        return sequence
    if placeholder == "sourcetype":
        return stream["sourcetype"]

    value = metric_value(cfg, section, prefix, local_dt)
    if value is None:
        return 0

    if placeholder in ("availability", "http_status_code"):
        return int(round(value))
    return round(value, 6)


def render_template(template_text, replacements):
    def _sub(match):
        key = match.group(1)
        value = replacements.get(key, "")
        if isinstance(value, (int, float)):
            return str(value)
        return str(value)

    rendered = PLACEHOLDER_RE.sub(_sub, template_text)
    return json.loads(rendered)


def clone_cfg(cfg):
    out = _new_cfg()
    for section in cfg.sections():
        out.add_section(section)
        for key, value in cfg.items(section):
            out.set(section, key, value)
    return out


def active_scenarios_for_tick(cfg, tick_ts):
    names = []
    if not cfg.has_section("scenarios"):
        return names
    for key, value in cfg.items("scenarios"):
        if not key.endswith("_activated"):
            continue
        try:
            activated = int(float(value))
        except Exception:
            activated = 0
        if activated <= 0:
            continue
        scenario_name = key[: -len("_activated")]
        fault_start = parse_int(cfg, "scenarios", f"{scenario_name}_fault_start", default=0) or 0
        fault_duration = parse_int(
            cfg, "scenarios", f"{scenario_name}_fault_duration", default=0
        ) or 0
        start = activated + (fault_start * 60)
        end = start + (fault_duration * 60)
        if tick_ts < start:
            continue
        if fault_duration > 0 and tick_ts >= end:
            continue
        if not cfg.has_section(scenario_name):
            continue
        names.append(scenario_name)
    names.sort()
    return names


def effective_cfg_for_tick(base_cfg, tick_ts):
    cfg = clone_cfg(base_cfg)
    active = active_scenarios_for_tick(base_cfg, tick_ts)
    if not cfg.has_section("baseline"):
        cfg.add_section("baseline")
    for scenario_name in active:
        for key, value in base_cfg.items(scenario_name):
            if "#" not in key:
                continue
            cfg.set("baseline", key, value)
    return cfg, active


def minute_due_for_interval(ts, interval_min):
    if interval_min <= 0:
        return False
    minute_of_hour = datetime.fromtimestamp(ts, tz=timezone.utc).minute
    return (minute_of_hour % interval_min) == 0


def generate_single_event(cfg, stream, ts, tzinfo, region, sequence):
    section = "baseline"
    prefix_base = f"{stream['index']}#{stream['sourcetype']}#"

    with open(stream["sample"], "r") as f:
        template_text = f.read()

    placeholders = sorted(set(PLACEHOLDER_RE.findall(template_text)))
    local_dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tzinfo)
    replacements = {}
    for ph in placeholders:
        prefix = f"{prefix_base}{ph}"
        replacements[ph] = coerce_placeholder(
            cfg, section, prefix, ph, local_dt, sequence, stream, region
        )

    if stream["index"] == "telemetry" and stream["sourcetype"] == "cnc_interface_counter_json":
        placeholder_index = index_telemetry_placeholders(placeholders)
        links = load_telemetry_bidirectional_links()
        if links:
            enforce_telemetry_directional_conservation(replacements, placeholder_index, links)

    return render_template(template_text, replacements)


def write_stream_events(stream, events):
    if not events:
        return None
    os.makedirs(stream["spool_dir"], exist_ok=True)
    output_path = os.path.join(
        stream["spool_dir"],
        f"live_{int(time.time() * 1_000_000)}_{os.getpid()}_{stream['index']}_{stream['sourcetype'].replace(':', '_')}.json",
    )
    with open(output_path, "w") as out:
        for event_obj in events:
            out.write(json.dumps(event_obj, separators=(",", ":")))
            out.write("\n")
    return output_path


def resolve_start_tick(base_cfg):
    anchor = parse_int(base_cfg, "baseline", "backfill_start_time", default=None)
    if anchor is None:
        return None, "missing baseline.backfill_start_time"

    first_tick = ((anchor + 59) // 60) * 60
    local_cfg = read_local_conf()
    last_tick = parse_int(local_cfg, "baseline", LIVE_CURSOR_KEY, default=None)
    if last_tick is not None:
        start_tick = max(first_tick, last_tick + 60)
        return start_tick, "resume_from_live_cursor"
    return first_tick, "start_from_backfill_anchor"


def persist_live_cursor(tick_ts):
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set("baseline", LIVE_CURSOR_KEY, str(int(tick_ts)))
    write_local_conf(local_cfg)


def process_tick(tick_ts, sequence_state):
    base_cfg = read_effective_conf()
    if not base_cfg.has_section("baseline"):
        return 0, [], {}

    tzinfo, region = get_region_tz(base_cfg)
    effective_cfg, active_scenarios = effective_cfg_for_tick(base_cfg, tick_ts)

    emitted = 0
    per_stream_counts = {}
    for stream in STREAMS:
        prefix_base = f"{stream['index']}#{stream['sourcetype']}#"
        interval = parse_int(effective_cfg, "baseline", f"{prefix_base}interval", default=1)
        interval = max(interval or 1, 1)
        if not minute_due_for_interval(tick_ts, interval):
            continue
        sequence_state["seq"] += 1
        event_obj = generate_single_event(
            effective_cfg, stream, tick_ts, tzinfo, region, sequence_state["seq"]
        )
        path = write_stream_events(stream, [event_obj])
        emitted += 1
        per_stream_counts[f"{stream['index']}#{stream['sourcetype']}"] = (
            per_stream_counts.get(f"{stream['index']}#{stream['sourcetype']}", 0) + 1
        )
        print(
            f"live_log: wrote 1 event to {path} "
            f"(tick={tick_ts} index={stream['index']} sourcetype={stream['sourcetype']} interval={interval})",
            flush=True,
        )

    return emitted, active_scenarios, per_stream_counts


def next_minute_sleep_seconds():
    now = time.time()
    next_minute = ((int(now) // 60) + 1) * 60
    return max(0.2, next_minute - now)


def main():
    base_cfg = read_effective_conf()
    start_tick, start_reason = resolve_start_tick(base_cfg)
    if start_tick is None:
        print("live_log: missing baseline.backfill_start_time; skipping", flush=True)
        write_generation_log("skip_missing_backfill_start_time")
        return

    tzinfo, region = get_region_tz(base_cfg)
    print(
        f"live_log: starting minute scheduler start_tick={start_tick} "
        f"region={region} tz={tzinfo.key} reason={start_reason}",
        flush=True,
    )
    write_generation_log(
        "start",
        start_tick=start_tick,
        region=region,
        timezone=tzinfo.key,
        start_reason=start_reason,
    )

    cursor = int(start_tick)
    sequence_state = {"seq": 0}

    while True:
        now_tick = (int(time.time()) // 60) * 60
        if cursor > now_tick:
            time.sleep(next_minute_sleep_seconds())
            continue

        total_emitted = 0
        active_seen = set()
        stream_totals = {}
        batch_start = cursor
        while cursor <= now_tick:
            emitted, active_scenarios, per_stream_counts = process_tick(
                cursor, sequence_state
            )
            total_emitted += emitted
            for name in active_scenarios:
                active_seen.add(name)
            for key, count in per_stream_counts.items():
                stream_totals[key] = stream_totals.get(key, 0) + count
            persist_live_cursor(cursor)
            cursor += 60

        write_generation_log(
            "tick_batch_processed",
            batch_start=batch_start,
            batch_end=now_tick,
            emitted_events=total_emitted,
            active_scenarios=sorted(active_seen),
            stream_totals=stream_totals,
        )
        if total_emitted == 0:
            print(
                f"live_log: tick batch {batch_start}->{now_tick} emitted no events",
                flush=True,
            )


if __name__ == "__main__":
    main()
