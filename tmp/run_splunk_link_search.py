#!/usr/bin/env python3
"""One-shot Splunk export for telemetry link search."""
import json
import os
import subprocess
import sys

import urllib.parse

TOKEN = json.load(open(os.path.expanduser("~/.cursor/mcp.json")))["mcpServers"][
    "splunk-mcp-server"
]["env"]["AUTH_TOKEN"]

SEARCH = r"""search index=telemetry sourcetype=cnc_interface_counter_json earliest=1778433900 latest=1778435700
| spath path=devices{} output=device 
| mvexpand device 
| spath input=device path=host_name output=host_name 
| spath input=device path=uuid output=uuid 
| rex field=device max_match=0 "\"(?<if_name>(?:HundredGigE|Bundle-Ether)[^\"]+)\"" 
| mvexpand if_name 
| eval ifInPktsRate = json_extract(device, "interfaces." . if_name . ".ifInPktsRate.latest_data.value") 
| eval ifOutPktsRate = json_extract(device, "interfaces." . if_name . ".ifOutPktsRate.latest_data.value") 
| eval timestamp = json_extract(device, "interfaces." . if_name . ".ifInPktsRate.latest_data.timestamp") 
| rename host_name as router1_name if_name as interface1 
| table _time router1_name interface1 ifInPktsRate ifOutPktsRate 
| bin span=1m _time 
| stats avg(ifInPktsRate) as ifInPktsRate1 avg(ifOutPktsRate) as ifOutPktsRate1 by _time router1_name interface1 
| join router1_name interface1 
    [ inputlookup router_if_connections.csv 
    | appendpipe 
        [ rename *1 as *tmp, router1_name as routertmp_name 
        | rename *2 as *1, router2_name as router1_name 
        | rename *tmp as *2, routertmp_name as router2_name ] ] 
| join type=inner _time router2_name interface2 
    [ search index=telemetry sourcetype=cnc_interface_counter_json earliest=1778433900 latest=1778435700
    | spath path=devices{} output=device 
    | mvexpand device 
    | spath input=device path=host_name output=host_name 
    | rex field=device max_match=0 "\"(?<if_name>(?:HundredGigE|Bundle-Ether)[^\"]+)\"" 
    | mvexpand if_name 
    | eval ifInPktsRate = json_extract(device, "interfaces." . if_name . ".ifInPktsRate.latest_data.value") 
    | eval ifOutPktsRate = json_extract(device, "interfaces." . if_name . ".ifOutPktsRate.latest_data.value") 
    | rename host_name as router2_name if_name as interface2 
    | table _time router2_name interface2 ifInPktsRate ifOutPktsRate 
    | bin span=1m _time 
    | stats avg(ifInPktsRate) as ifInPktsRate2 avg(ifOutPktsRate) as ifOutPktsRate2 by _time router2_name interface2 ] 
| eval path = router1.":".interface1."_".router2.":".interface2 
| search path="R6:HundredGigE0/1/0/0_R4:HundredGigE0/0/2/0" 
| eval ifOutPktsRate1 = round(ifOutPktsRate1, 2) 
| eval ifInPktsRate2 = round(ifInPktsRate2, 2) 
| timechart span=1m useother=f limit=30 avg(ifOutPktsRate1) as ifOutPktsRate avg(ifInPktsRate2) as ifInPktsRate by path"""

def main():
    data = urllib.parse.urlencode(
        {
            "search": SEARCH,
            "exec_mode": "oneshot",
            "output_mode": "json",
        }
    )
    cmd = [
        "curl",
        "-sk",
        "-H",
        f"Authorization: Bearer {TOKEN}",
        "-X",
        "POST",
        "--data-binary",
        data,
        "https://127.0.0.1:8089/servicesNS/nobody/ai_lab/search/jobs/export",
    ]
    out = subprocess.check_output(cmd, text=True)
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except json.JSONDecodeError:
            print("NON-JSON LINE:", line[:300], file=sys.stderr)
            continue
        # jobs/export streams {"preview":false,"lastrow":false,"result":{...}}
        if "result" in j:
            rows.append(j["result"])
        elif isinstance(j, dict) and "_time" in j:
            rows.append(j)

    print(f"pulled {len(rows)} result rows\n")
    for r in rows:
        ts = r.get("_time") or r.get("time") or ""
        print(json.dumps({k: r.get(k) for k in sorted(r.keys())[:20]}))


if __name__ == "__main__":
    main()
