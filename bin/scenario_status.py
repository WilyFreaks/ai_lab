import os
import sys
import time
from configparser import ConfigParser
from datetime import datetime
from zoneinfo import ZoneInfo
import splunk.Intersplunk as isp


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")

REGION_TZ = {
    "au": "Australia/Sydney",
    "jp": "Asia/Tokyo",
}
FALLBACK_TZ = "UTC"


def read_effective_config():
    cfg = ConfigParser(interpolation=None, delimiters=("=",), strict=False)
    if os.path.exists(DEFAULT_CONF):
        cfg.read(DEFAULT_CONF)
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    return cfg


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

        if not scenario:
            isp.outputResults([{"status": "error", "message": "scenario is required"}])
            return

        cfg = read_effective_config()

        activated_raw = cfg.get("scenarios", f"{scenario}_activated", fallback="0").strip()
        try:
            activated_int = int(float(activated_raw))
        except (TypeError, ValueError):
            activated_int = 0

        region = cfg.get("baseline", "region", fallback="").strip().lower()
        tz_name = REGION_TZ.get(region, FALLBACK_TZ)
        tzinfo = ZoneInfo(tz_name)

        if activated_int > 0:
            status = "activated"
            activation_local_time = datetime.fromtimestamp(activated_int, tz=tzinfo).strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
        else:
            status = "deactivated"
            activation_local_time = ""

        isp.outputResults(
            [
                {
                    "scenario": scenario,
                    "status": status,
                    "activation_local_time": activation_local_time,
                }
            ]
        )
    except Exception as e:
        isp.outputResults([{"status": "error", "message": str(e)}])


if __name__ == "__main__":
    main()
