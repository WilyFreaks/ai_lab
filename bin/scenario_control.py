import glob
import os
import sys
import time
from configparser import ConfigParser

# splunklib is not shipped under etc/apps/search/bin on all installs; add known bundle paths.
SPLUNK_HOME = os.environ.get("SPLUNK_HOME", "/Applications/Splunk")
_APP_BIN = os.path.dirname(os.path.abspath(__file__))
for _d in (
    _APP_BIN,
    os.path.join(SPLUNK_HOME, "etc", "apps", "search", "bin"),
    os.path.join(SPLUNK_HOME, "etc", "apps", "Splunk_MCP_Server", "bin"),
    os.path.join(SPLUNK_HOME, "etc", "apps", "splunk_secure_gateway", "lib"),
) + tuple(
    sorted(glob.glob(os.path.join(SPLUNK_HOME, "etc", "apps", "Splunk_SA_Scientific_Python_*", "lib")))
):
    if _d and os.path.isfile(os.path.join(_d, "splunklib", "__init__.py")):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break

from splunklib.searchcommands import Configuration, GeneratingCommand, Option, dispatch


APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONF = os.path.join(APP_ROOT, "default", "ai_lab_scenarios.conf")
LOCAL_CONF = os.path.join(APP_ROOT, "local", "ai_lab_scenarios.conf")


def load_config():
    cfg = ConfigParser()
    if os.path.exists(LOCAL_CONF):
        cfg.read(LOCAL_CONF)
    else:
        cfg.read(DEFAULT_CONF)
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(LOCAL_CONF), exist_ok=True)
    with open(LOCAL_CONF, "w") as f:
        cfg.write(f)


@Configuration()
class ScenarioControlCommand(GeneratingCommand):
    scenario = Option(require=True)
    active = Option(require=True)
    fault_start = Option(require=False)
    fault_duration = Option(require=False)

    def generate(self):
        scenario = self.scenario.strip()
        if not scenario:
            yield {"status": "error", "message": "scenario is required"}
            return

        if self.active not in ("0", "1"):
            yield {"status": "error", "message": "active must be 0 or 1"}
            return

        cfg = load_config()
        if not cfg.has_section("scenarios"):
            cfg.add_section("scenarios")

        activated = str(int(time.time())) if self.active == "1" else "0"
        cfg.set("scenarios", f"{scenario}_activated", activated)

        if self.fault_start is not None and self.fault_start != "":
            cfg.set("scenarios", f"{scenario}_fault_start", str(int(float(self.fault_start))))
        if self.fault_duration is not None and self.fault_duration != "":
            cfg.set("scenarios", f"{scenario}_fault_duration", str(int(float(self.fault_duration))))
        save_config(cfg)

        yield {
            "status": "ok",
            "scenario": scenario,
            "active": self.active,
            "activated": activated,
            "fault_start": cfg.get("scenarios", f"{scenario}_fault_start", fallback=""),
            "fault_duration": cfg.get("scenarios", f"{scenario}_fault_duration", fallback=""),
            "config_path": LOCAL_CONF,
        }


dispatch(ScenarioControlCommand, module_name=__name__)
