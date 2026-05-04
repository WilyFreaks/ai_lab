import os
import subprocess
import sys
import json
import time
from configparser import ConfigParser
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import splunk.Intersplunk as isp


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
BIN_DIR = os.path.join(APP_ROOT, "bin")
SPOOL_LOG_DIR = os.path.join(
    APP_ROOT, "var", "spool", "ai_lab", "ai_lab_log", "workshop_region"
)
VALID_REGIONS = {"au", "jp"}
REGION_TZ = {
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
}


def _new_cfg():
    # ai_lab keys include ":" inside option names (e.g. cisco:thousandeyes);
    # force "=" as the only delimiter to avoid parser collisions.
    return ConfigParser(interpolation=None, delimiters=("=",), strict=False)


def load_effective_config():
    cfg = _new_cfg()
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def load_local_config():
    cfg = _new_cfg()
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def save_local_config(local_cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        local_cfg.write(f)


def normalized_region(value):
    if value is None:
        return ""
    return value.strip().lower()


def is_generation_enabled(cfg):
    return (
        cfg.get("baseline", "baseline_generation_enabled", fallback="false")
        .strip()
        .lower()
        == "true"
    )


def parse_int(value, default=None):
    try:
        return int(float(value))
    except Exception:
        return default


def _format_local_time(epoch_ts, region):
    if epoch_ts in (None, ""):
        return ""
    tz_name = REGION_TZ.get(region, "UTC")
    dt = datetime.fromtimestamp(int(epoch_ts), tz=ZoneInfo(tz_name))
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def _backfill_times(cfg, region):
    anchor_raw = cfg.get("baseline", "backfill_start_time", fallback="")
    days = parse_int(cfg.get("baseline", "backfill_days", fallback="7"), default=7) or 7
    anchor = parse_int(anchor_raw, default=None)
    head = anchor - (days * 86400) if anchor is not None else None
    return {
        "backfill_head_time": "" if head is None else str(head),
        "backfill_head_time_local": _format_local_time(head, region),
        "backfill_start_time": "" if anchor is None else str(anchor),
        "backfill_start_time_local": _format_local_time(anchor, region),
    }


def _backfill_wall_clock_fields(cfg, region_for_local_fmt):
    """
    Fields populated by backfill_log: run start / completion wall times and duration (seconds).
    """
    rs = cfg.get("baseline", "backfill_run_started_time", fallback="").strip()
    ce = cfg.get("baseline", "backfill_completed_time", fallback="").strip()
    started = parse_int(rs, default=None)
    completed = parse_int(ce, default=None)
    out = {
        "backfill_run_started_time": rs,
        "backfill_run_started_time_local": _format_local_time(started, region_for_local_fmt),
        "backfill_completed_time": ce,
        "backfill_completed_time_local": _format_local_time(completed, region_for_local_fmt),
        "backfill_duration": "",
    }
    if (
        cfg.get("baseline", "backfill_completed", fallback="").strip().lower() == "true"
        and started is not None
        and completed is not None
    ):
        out["backfill_duration"] = str(max(0, completed - started))
    return out


def _backfill_completed_if_set(cfg):
    if cfg.has_section("baseline") and cfg.has_option("baseline", "backfill_completed"):
        return cfg.get("baseline", "backfill_completed", fallback="").strip()
    return None


def ensure_backfill_timing_on_set(local_cfg):
    if not local_cfg.has_section("baseline"):
        local_cfg.add_section("baseline")

    current = local_cfg.get("baseline", "backfill_start_time", fallback="").strip()
    if parse_int(current, default=None) is not None:
        return False

    now = str(int(time.time()))
    local_cfg.set("baseline", "backfill_start_time", now)
    if not local_cfg.has_option("baseline", "backfill_completed"):
        local_cfg.set("baseline", "backfill_completed", "false")
    return True


def launcher_path():
    return os.path.join(BIN_DIR, "launcher.py")


def maybe_launch_generation():
    path = launcher_path()
    if not os.path.exists(path):
        return False, f"launcher not found: {path}"

    # Detached launch from command context; launcher itself applies safety gate.
    subprocess.Popen(
        [sys.executable, path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True, "launcher triggered"


def parse_args(argv):
    args = {}
    for token in argv[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        args[key.strip().lower()] = value.strip().strip("\"'")
    return args


def write_result_spool(action, rows):
    os.makedirs(SPOOL_LOG_DIR, exist_ok=True)
    path = os.path.join(
        SPOOL_LOG_DIR, f"workshop_region_{int(time.time() * 1_000_000)}_{os.getpid()}.json"
    )
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": "workshop_region",
        "action": action,
        "result_count": len(rows),
        "results": rows,
    }
    with open(path, "w") as f:
        f.write(json.dumps(event, separators=(",", ":")))
        f.write("\n")


def main():
    try:
        args = parse_args(sys.argv)
        action = args.get("action", "get").strip().lower()

        if action not in ("get", "set", "status"):
            rows = [{"status": "error", "message": "action must be get, set, or status"}]
            write_result_spool(action, rows)
            isp.outputResults(rows)
            return

        if action in ("get", "status"):
            cfg = load_effective_config()
            configured_region = normalized_region(cfg.get("baseline", "region", fallback=""))
            region_ready = configured_region in VALID_REGIONS
            # Local-time fields use REGION_TZ; unknown / unpersisted region -> UTC (_format_local_time).
            tz_region = configured_region if region_ready else ""
            backfill_times = _backfill_times(cfg, tz_region)
            wall = _backfill_wall_clock_fields(cfg, tz_region)
            row = {
                "status": "ok",
                "action": action,
                # region is the explicitly configured persisted value (blank until valid au/jp in conf).
                "region": configured_region if region_ready else "",
                "region_ready": str(region_ready).lower(),
                "baseline_generation_enabled": str(is_generation_enabled(cfg)).lower(),
                "backfill_start_time": backfill_times["backfill_start_time"],
                "backfill_start_time_local": backfill_times["backfill_start_time_local"],
                "backfill_head_time": backfill_times["backfill_head_time"],
                "backfill_head_time_local": backfill_times["backfill_head_time_local"],
                "backfill_run_started_time": wall["backfill_run_started_time"],
                "backfill_run_started_time_local": wall["backfill_run_started_time_local"],
                "backfill_completed_time": wall["backfill_completed_time"],
                "backfill_completed_time_local": wall["backfill_completed_time_local"],
                "backfill_duration": wall["backfill_duration"],
            }
            backfill_completed = _backfill_completed_if_set(cfg)
            if backfill_completed is not None:
                row["backfill_completed"] = backfill_completed
            rows = [row]
            write_result_spool(action, rows)
            isp.outputResults(rows)
            return

        region = normalized_region(args.get("region", ""))
        if region not in VALID_REGIONS:
            rows = [{"status": "error", "message": "region must be one of: au, jp"}]
            write_result_spool(action, rows)
            isp.outputResults(rows)
            return

        local_cfg = load_local_config()
        if not local_cfg.has_section("baseline"):
            local_cfg.add_section("baseline")

        local_cfg.set("baseline", "region", region)
        local_cfg.set("baseline", "baseline_generation_enabled", "true")
        changed = ensure_backfill_timing_on_set(local_cfg)
        save_local_config(local_cfg)
        launched, launch_message = maybe_launch_generation()
        effective_cfg = load_effective_config()
        backfill_times = _backfill_times(effective_cfg, region)
        wall = _backfill_wall_clock_fields(effective_cfg, region)
        row = {
            "status": "ok",
            "action": "set",
            "region": region,
            "region_ready": "true",
            "baseline_generation_enabled": "true",
            "launcher_triggered": str(launched).lower(),
            "launcher_message": launch_message,
            "initial_backfill": str(changed).lower(),
            "backfill_start_time": backfill_times["backfill_start_time"],
            "backfill_start_time_local": backfill_times["backfill_start_time_local"],
            "backfill_head_time": backfill_times["backfill_head_time"],
            "backfill_head_time_local": backfill_times["backfill_head_time_local"],
            "backfill_run_started_time": wall["backfill_run_started_time"],
            "backfill_run_started_time_local": wall["backfill_run_started_time_local"],
            "backfill_completed_time": wall["backfill_completed_time"],
            "backfill_completed_time_local": wall["backfill_completed_time_local"],
            "backfill_duration": wall["backfill_duration"],
        }
        backfill_completed = _backfill_completed_if_set(effective_cfg)
        if backfill_completed is not None:
            row["backfill_completed"] = backfill_completed
        rows = [row]
        write_result_spool(action, rows)
        isp.outputResults(rows)
    except Exception as e:
        rows = [{"status": "error", "message": str(e)}]
        write_result_spool("exception", rows)
        isp.outputResults(rows)


if __name__ == "__main__":
    main()
