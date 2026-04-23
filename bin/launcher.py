import os
import subprocess
import sys
import time
from configparser import ConfigParser, NoOptionError

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
BIN_DIR = os.path.join(APP_ROOT, "bin")
VALID_REGIONS = {"au", "jp"}


def read_local_conf():
    cfg = ConfigParser(interpolation=None, delimiters=("=",), strict=False)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


def read_default_conf():
    cfg = ConfigParser(interpolation=None, delimiters=("=",), strict=False)
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    return cfg


def write_local_conf(cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        cfg.write(f)


def ensure_backfill_start_time(cfg):
    if not cfg.has_section("baseline"):
        cfg.add_section("baseline")

    try:
        cfg.get("baseline", "backfill_start_time")
    except NoOptionError:
        now = str(int(time.time()))
        cfg.set("baseline", "backfill_start_time", now)
        cfg.set("baseline", "backfill_completed", "false")
        write_local_conf(cfg)
        print(f"launcher: backfill_start_time set to {now}", flush=True)


def ensure_scenario_activation_keys(local_cfg):
    default_cfg = read_default_conf()
    if not default_cfg.has_section("scenarios"):
        return

    changed = False
    if not local_cfg.has_section("scenarios"):
        local_cfg.add_section("scenarios")
        changed = True

    for key, default_value in default_cfg.items("scenarios"):
        if not key.endswith("_activated"):
            continue
        if not local_cfg.has_option("scenarios", key):
            local_cfg.set("scenarios", key, default_value)
            changed = True

    if changed:
        write_local_conf(local_cfg)
        print("launcher: initialized missing scenario_*_activated keys", flush=True)


def generation_gate_open(cfg):
    if not cfg.has_section("baseline"):
        return False, "missing [baseline] stanza"

    region = cfg.get("baseline", "region", fallback="").strip().lower()
    if region not in VALID_REGIONS:
        return False, "region is not set (expected au/jp)"

    enabled = cfg.get("baseline", "baseline_generation_enabled", fallback="false")
    if str(enabled).strip().lower() != "true":
        return False, "baseline_generation_enabled is not true"

    return True, f"region={region}"


def spawn(script_name):
    script_path = os.path.join(BIN_DIR, script_name)
    proc = subprocess.Popen(
        [sys.executable, script_path],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    print(f"launcher: spawned {script_name} (pid={proc.pid})", flush=True)
    return proc


def main():
    cfg = read_local_conf()
    gate_ok, reason = generation_gate_open(cfg)
    if not gate_ok:
        print(f"launcher: generation gate closed ({reason}); exiting", flush=True)
        return

    print(f"launcher: generation gate open ({reason})", flush=True)
    ensure_backfill_start_time(cfg)
    ensure_scenario_activation_keys(cfg)

    backfill_proc = spawn("backfill_log.py")
    live_proc = spawn("live_log.py")

    backfill_proc.wait()
    live_proc.wait()


if __name__ == "__main__":
    main()
