import json
import os
import random
import re
import time
import csv
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
    # Prefer the newly introduced filename when present, but support the legacy one.
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


def interface_to_placeholder_token(interface_name):
    token = str(interface_name).strip()
    # Keep Bundle-Ether semantic token while converting path separators.
    token = token.replace("Bundle-Ether", "Bundle_Ether")
    token = token.replace("/", "_")
    return token


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
    # Enforce packet-loss-only model (no packet creation in transit) and
    # bound modeled drop rate under 1% per link direction:
    #   0 <= (ifOut - ifIn_peer) / ifOut < 0.01
    # For non-positive ifOut, force ifIn to match ifOut.
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
    # ai_lab keys contain ":" characters; force "=" delimiter only.
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
        "component": "backfill_log",
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
    # {{timestamp}} is a region-local wall-clock string, with a fixed or zone-derived suffix.
    # - jp: always "JST" (Asia/Tokyo has no DST)
    # - au: use Australia/Sydney's current abbreviation (AEST in standard time, AEDT during DST)
    #       We do not hardcode "AEST" year-round, because that would be wrong during summer time.
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
    # Smooth Fri->Sat and Sun->Mon transitions to avoid abrupt metric jumps.
    weekday = local_dt.weekday()  # Mon=0 .. Sun=6
    hour = local_dt.hour + (local_dt.minute / 60.0)

    weekend_weight = 0.0
    # Ramp up from Friday 18:00 to Saturday 00:00.
    if weekday == 4 and hour >= 18.0:
        weekend_weight = min(max((hour - 18.0) / 6.0, 0.0), 1.0)
    # Full weekend on Saturday.
    elif weekday == 5:
        weekend_weight = 1.0
    # Sunday: full weekend until 18:00, then ramp down to Monday 00:00.
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
        # Sample templates use {{timestamp}} as a domain timestamp string; it must reflect
        # the selected workshop region's local wall time (not UTC), with a short TZ suffix.
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
    # Ensure each line is valid JSON before writing.
    return json.loads(rendered)


def generate_stream(cfg, stream, start_ts, end_ts, tzinfo, region):
    section = "baseline"
    prefix_base = f"{stream['index']}#{stream['sourcetype']}#"
    interval = parse_int(cfg, section, f"{prefix_base}interval", default=1)
    interval = max(interval or 1, 1)

    with open(stream["sample"], "r") as f:
        template_text = f.read()

    placeholders = sorted(set(PLACEHOLDER_RE.findall(template_text)))
    telemetry_placeholder_index = {}
    telemetry_links = []
    if stream["index"] == "telemetry" and stream["sourcetype"] == "cnc_interface_counter_json":
        telemetry_placeholder_index = index_telemetry_placeholders(placeholders)
        telemetry_links = load_telemetry_bidirectional_links()
    os.makedirs(stream["spool_dir"], exist_ok=True)
    output_path = os.path.join(
        stream["spool_dir"],
        f"backfill_{int(time.time() * 1_000_000)}_{os.getpid()}_{stream['index']}_{stream['sourcetype'].replace(':', '_')}.json",
    )

    sequence = 1
    step = interval * 60
    count = 0
    with open(output_path, "w") as out:
        for ts in range(start_ts, end_ts, step):
            local_dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tzinfo)
            replacements = {}
            for ph in placeholders:
                prefix = f"{prefix_base}{ph}"
                replacements[ph] = coerce_placeholder(
                    cfg, section, prefix, ph, local_dt, sequence, stream, region
                )
            if telemetry_links:
                enforce_telemetry_directional_conservation(
                    replacements, telemetry_placeholder_index, telemetry_links
                )
            event_obj = render_template(template_text, replacements)
            out.write(json.dumps(event_obj, separators=(",", ":")))
            out.write("\n")
            sequence += 1
            count += 1

    print(
        f"backfill_log: wrote {count} events to {output_path} "
        f"(index={stream['index']} sourcetype={stream['sourcetype']})",
        flush=True,
    )
    write_generation_log(
        "stream_written",
        index=stream["index"],
        sourcetype=stream["sourcetype"],
        events=count,
        output_path=output_path,
    )


def mark_backfill_completed():
    local_cfg = read_local_conf()
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")
    local_cfg.set("baseline", "backfill_completed", "true")
    write_local_conf(local_cfg)


def main():
    cfg = read_effective_conf()

    start_anchor = parse_int(cfg, "baseline", "backfill_start_time", default=None)
    if start_anchor is None:
        print("backfill_log: missing baseline.backfill_start_time; skipping", flush=True)
        write_generation_log("skip_missing_backfill_start_time")
        return

    completed = cfg.get("baseline", "backfill_completed", fallback="false").strip().lower()
    if completed == "true":
        print("backfill_log: already completed; skipping", flush=True)
        write_generation_log("skip_already_completed")
        return

    backfill_days = parse_int(cfg, "baseline", "backfill_days", default=7) or 7
    start_ts = start_anchor - (backfill_days * 86400)
    end_ts = start_anchor

    tzinfo, region = get_region_tz(cfg)
    print(
        f"backfill_log: starting backfill window start={start_ts} end={end_ts} "
        f"days={backfill_days} region={region} tz={tzinfo.key}",
        flush=True,
    )
    write_generation_log(
        "start",
        backfill_start_time=start_anchor,
        start_ts=start_ts,
        end_ts=end_ts,
        backfill_days=backfill_days,
        region=region,
        timezone=tzinfo.key,
    )

    for stream in STREAMS:
        generate_stream(cfg, stream, start_ts, end_ts, tzinfo, region)

    mark_backfill_completed()
    print("backfill_log: completed", flush=True)
    write_generation_log(
        "completed",
        backfill_start_time=start_anchor,
        start_ts=start_ts,
        end_ts=end_ts,
        backfill_days=backfill_days,
        region=region,
        timezone=tzinfo.key,
    )


if __name__ == "__main__":
    main()
