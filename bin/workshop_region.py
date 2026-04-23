import os
import subprocess
import sys
from configparser import ConfigParser

import splunk.Intersplunk as isp


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
BIN_DIR = os.path.join(APP_ROOT, "bin")
VALID_REGIONS = {"au", "jp"}


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


def effective_region(cfg):
    region = normalized_region(cfg.get("baseline", "region", fallback=""))
    if region in VALID_REGIONS:
        return region
    return "au"


def is_generation_enabled(cfg):
    return (
        cfg.get("baseline", "baseline_generation_enabled", fallback="false")
        .strip()
        .lower()
        == "true"
    )


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


def main():
    try:
        args = parse_args(sys.argv)
        action = args.get("action", "get").strip().lower()

        if action not in ("get", "set", "status"):
            isp.outputResults(
                [{"status": "error", "message": "action must be get, set, or status"}]
            )
            return

        if action in ("get", "status"):
            cfg = load_effective_config()
            configured_region = normalized_region(cfg.get("baseline", "region", fallback=""))
            region_ready = configured_region in VALID_REGIONS
            isp.outputResults([
                {
                    "status": "ok",
                    "action": action,
                    # region is the explicitly configured value (can be blank).
                    "region": configured_region if region_ready else "",
                    # effective_region is runtime fallback-safe value for generators.
                    "effective_region": effective_region(cfg),
                    "region_ready": str(region_ready).lower(),
                    "baseline_generation_enabled": str(is_generation_enabled(cfg)).lower(),
                    "backfill_start_time": cfg.get(
                        "baseline", "backfill_start_time", fallback=""
                    ),
                    "backfill_completed": cfg.get(
                        "baseline", "backfill_completed", fallback=""
                    ),
                    "config_path": LOCAL_CONF if os.path.exists(LOCAL_CONF) else DEFAULT_CONF,
                }
            ])
            return

        region = normalized_region(args.get("region", ""))
        if region not in VALID_REGIONS:
            isp.outputResults([{"status": "error", "message": "region must be one of: au, jp"}])
            return

        local_cfg = load_local_config()
        if not local_cfg.has_section("baseline"):
            local_cfg.add_section("baseline")

        local_cfg.set("baseline", "region", region)
        local_cfg.set("baseline", "baseline_generation_enabled", "true")
        save_local_config(local_cfg)
        launched, launch_message = maybe_launch_generation()

        isp.outputResults([
            {
                "status": "ok",
                "action": "set",
                "region": region,
                "baseline_generation_enabled": "true",
                "launcher_triggered": str(launched).lower(),
                "launcher_message": launch_message,
                "config_path": LOCAL_CONF,
            }
        ])
    except Exception as e:
        isp.outputResults([{"status": "error", "message": str(e)}])


if __name__ == "__main__":
    main()
