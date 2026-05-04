import os
import signal
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


def running_pids_for_script(script_name):
    script_path = os.path.join(BIN_DIR, script_name)
    script_real = os.path.realpath(script_path)
    pids = []

    # Use process table inspection to avoid launching duplicate workers.
    ps = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    )
    if ps.returncode != 0:
        return pids

    for line in ps.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            continue

        try:
            pid = int(parts[0])
        except ValueError:
            continue

        if pid == os.getpid():
            continue

        args = parts[1]
        argv = args.split()
        for token in argv:
            token_real = os.path.realpath(token)
            if token_real == script_real or os.path.basename(token_real) == script_name:
                pids.append(pid)
                break

    return pids


def _ps_field(pid, field):
    """Single-column ps output (e.g. ppid=, args=). Works on macOS/BSD."""
    r = subprocess.run(
        ["ps", "-p", str(int(pid)), "-o", f"{field}="],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return ""
    return (r.stdout or "").strip()


def _orphan_generator_pid(pid):
    """
    True if this worker should be torn down before (re)spawn.

    Stale live_log/backfill often survives a Splunk restart (reparented to pid 1); launcher
    previously skipped spawn when it saw any matching PID and left the old code running.
    Legitimate workers have a live parent whose command line is launcher.py or splunkd.
    """
    ppid_s = _ps_field(pid, "ppid")
    if not ppid_s:
        return True
    try:
        ppid = int(ppid_s)
    except ValueError:
        return True
    if ppid <= 1:
        return True
    try:
        os.kill(ppid, 0)
    except OSError:
        return True
    pcmd = _ps_field(ppid, "args").lower()
    if "launcher.py" in pcmd:
        return False
    if "splunkd" in pcmd:
        return False
    return True


def terminate_pid(pid, label):
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"launcher: {label} pid={pid} SIGTERM failed: {e}", flush=True)
        return
    for _ in range(20):
        time.sleep(0.1)
        try:
            os.kill(pid, 0)
        except OSError:
            print(f"launcher: stopped {label} pid={pid}", flush=True)
            return
    try:
        os.kill(pid, signal.SIGKILL)
        print(f"launcher: force-killed {label} pid={pid}", flush=True)
    except OSError as e:
        print(f"launcher: {label} pid={pid} SIGKILL failed: {e}", flush=True)


def reap_stale_generators(script_name):
    """SIGTERM orphan backfill/live PIDs so a fresh Splunk launch can start new workers."""
    for pid in running_pids_for_script(script_name):
        if _orphan_generator_pid(pid):
            print(
                f"launcher: stale {script_name} (pid={pid}); terminating before (re)spawn",
                flush=True,
            )
            terminate_pid(pid, script_name)


def main():
    cfg = read_local_conf()
    gate_ok, reason = generation_gate_open(cfg)
    if not gate_ok:
        print(f"launcher: generation gate closed ({reason}); exiting", flush=True)
        return

    print(f"launcher: generation gate open ({reason})", flush=True)
    ensure_backfill_start_time(cfg)
    ensure_scenario_activation_keys(cfg)

    started_procs = []
    for script_name in ("backfill_log.py", "live_log.py"):
        reap_stale_generators(script_name)
        running_pids = running_pids_for_script(script_name)
        if running_pids:
            print(
                f"launcher: {script_name} already running (pid={','.join(str(pid) for pid in running_pids)}); skipping spawn",
                flush=True,
            )
            continue
        started_procs.append(spawn(script_name))

    if not started_procs:
        print("launcher: no new processes started", flush=True)
        return

    for proc in started_procs:
        proc.wait()


if __name__ == "__main__":
    main()
