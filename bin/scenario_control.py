import os
import sys
import time
from configparser import ConfigParser
import splunk.Intersplunk as isp


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")


def load_config():
    # ai_lab keys include ":" inside option names (e.g. cisco:thousandeyes);
    # force "=" as the only delimiter to avoid parser collisions.
    cfg = ConfigParser(interpolation=None, delimiters=("=",), strict=False)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    else:
        cfg.read(DEFAULT_CONF)
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


def main():
    try:
        args = parse_args(sys.argv)
        scenario = args.get("scenario", "").strip()
        active = args.get("active")
        fault_start = args.get("fault_start")
        fault_duration = args.get("fault_duration")

        if not scenario:
            isp.outputResults([{"status": "error", "message": "scenario is required"}])
            return

        if active not in ("0", "1"):
            isp.outputResults([{"status": "error", "message": "active must be 0 or 1"}])
            return

        cfg = load_config()
        if not cfg.has_section("scenarios"):
            cfg.add_section("scenarios")

        activated = str(int(time.time())) if active == "1" else "0"
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
