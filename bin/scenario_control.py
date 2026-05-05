import os
import sys
import time
from configparser import ConfigParser
import splunk.Intersplunk as isp


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")


def _new_cfg():
    return ConfigParser(interpolation=None, delimiters=("=",), strict=False)


def read_for_write():
    """Local if present; else default (first-time write seeds local)."""
    cfg = _new_cfg()
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
        return cfg
    cfg.read(DEFAULT_CONF)
    return cfg


def read_effective_config():
    """default overlaid by local — same shape as workshop_region / live effective reads."""
    cfg = _new_cfg()
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        cfg.write(f)


def parse_args(argv):
    args = {}
    for token in argv[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        args[key.strip().lower()] = value.strip().strip("\"'")
    return args


def output_status_row(scenario, cfg):
    if not cfg.has_section("scenarios"):
        activated = "0"
        fault_start = "0"
        fault_duration = "0"
    else:
        activated = cfg.get("scenarios", f"{scenario}_activated", fallback="0").strip()
        fault_start = cfg.get("scenarios", f"{scenario}_fault_start", fallback="0").strip()
        fault_duration = cfg.get("scenarios", f"{scenario}_fault_duration", fallback="0").strip()

    try:
        act_int = int(float(activated))
    except (TypeError, ValueError):
        act_int = 0
    active_ui = "1" if act_int > 0 else "0"

    isp.outputResults(
        [
            {
                "status": "ok",
                "message": "read_only",
                "scenario": scenario,
                "active": active_ui,
                "activated": str(act_int) if act_int > 0 else "0",
                "fault_start": fault_start,
                "fault_duration": fault_duration,
                "config_path": LOCAL_CONF,
            }
        ]
    )


def main():
    try:
        args = parse_args(sys.argv)
        scenario = args.get("scenario", "").strip()
        action = (args.get("action") or "").strip().lower()

        if not scenario:
            isp.outputResults([{"status": "error", "message": "scenario is required"}])
            return

        if action in ("status", "get"):
            cfg = read_effective_config()
            output_status_row(scenario, cfg)
            return

        if action not in ("", "set"):
            isp.outputResults(
                [{"status": "error", "message": f"unknown action '{action}' (use status|get|set)"}]
            )
            return

        # --- action=set (default): require active 0/1 and persist ---
        active = args.get("active")
        fault_start = args.get("fault_start")
        fault_duration = args.get("fault_duration")

        if active not in ("0", "1"):
            isp.outputResults([{"status": "error", "message": "active must be 0 or 1"}])
            return

        cfg = read_for_write()
        if not cfg.has_section("scenarios"):
            cfg.add_section("scenarios")

        existing_activated_raw = cfg.get("scenarios", f"{scenario}_activated", fallback="0").strip()
        try:
            existing_activated_int = int(float(existing_activated_raw))
        except (TypeError, ValueError):
            existing_activated_int = 0

        if active == "1":
            # Preserve an already-active scenario timestamp so repeated submits do not
            # retrigger or shift the active fault window start.
            activated = str(existing_activated_int) if existing_activated_int > 0 else str(int(time.time()))
        else:
            activated = "0"
        cfg.set("scenarios", f"{scenario}_activated", activated)

        if fault_start is not None and fault_start != "":
            cfg.set("scenarios", f"{scenario}_fault_start", str(int(float(fault_start))))
        if fault_duration is not None and fault_duration != "":
            cfg.set(
                "scenarios",
                f"{scenario}_fault_duration",
                str(int(float(fault_duration))),
            )
        save_config(cfg)

        isp.outputResults(
            [
                {
                    "status": "ok",
                    "message": "saved",
                    "scenario": scenario,
                    "active": active,
                    "activated": activated,
                    "fault_start": cfg.get(
                        "scenarios", f"{scenario}_fault_start", fallback=""
                    ),
                    "fault_duration": cfg.get(
                        "scenarios", f"{scenario}_fault_duration", fallback=""
                    ),
                    "config_path": LOCAL_CONF,
                }
            ]
        )
    except Exception as e:
        isp.outputResults([{"status": "error", "message": str(e)}])


if __name__ == "__main__":
    main()
