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


def get_region_tz(cfg):
    region = cfg.get("baseline", "region", fallback="").strip().lower()
    tz_name = REGION_TZ.get(region, "UTC")
    return ZoneInfo(tz_name), region or "unknown"


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
    # Simplified weekend handling for initial implementation.
    if configured is None:
        return 1.0
    return configured if local_dt.weekday() >= 5 else 1.0


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


def coerce_placeholder(cfg, section, prefix, placeholder, local_dt, sequence, stream):
    if placeholder == "timestamp":
        # Sample templates use {{timestamp}} as a domain timestamp string; it must reflect
        # the selected workshop region's local wall time (not UTC).
        return local_dt.strftime("%Y-%m-%dT%H:%M:%S")
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


def generate_stream(cfg, stream, start_ts, end_ts, tzinfo):
    section = "baseline"
    prefix_base = f"{stream['index']}#{stream['sourcetype']}#"
    interval = parse_int(cfg, section, f"{prefix_base}interval", default=1)
    interval = max(interval or 1, 1)

    with open(stream["sample"], "r") as f:
        template_text = f.read()

    placeholders = sorted(set(PLACEHOLDER_RE.findall(template_text)))
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
                    cfg, section, prefix, ph, local_dt, sequence, stream
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
        return

    completed = cfg.get("baseline", "backfill_completed", fallback="false").strip().lower()
    if completed == "true":
        print("backfill_log: already completed; skipping", flush=True)
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

    for stream in STREAMS:
        generate_stream(cfg, stream, start_ts, end_ts, tzinfo)

    mark_backfill_completed()
    print("backfill_log: completed", flush=True)


if __name__ == "__main__":
    main()
