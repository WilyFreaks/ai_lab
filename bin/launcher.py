import os
import subprocess
import sys
import time
from configparser import ConfigParser, NoOptionError

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")
BIN_DIR = os.path.join(APP_ROOT, "bin")


def read_local_conf():
    cfg = ConfigParser()
    cfg.read(LOCAL_CONF)
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
    ensure_backfill_start_time(cfg)

    backfill_proc = spawn("backfill_log.py")
    live_proc = spawn("live_log.py")

    backfill_proc.wait()
    live_proc.wait()


if __name__ == "__main__":
    main()
