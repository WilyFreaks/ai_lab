#!/usr/bin/env bash
python3 <<'PY'
import glob
from pathlib import Path

skills_root = Path.home() / ".cursor" / "skills-cursor"
skill_paths = sorted(glob.glob(str(skills_root / "*" / "SKILL.md")))
project_skill_paths = sorted(glob.glob(str(Path.cwd() / ".cursor" / "skills" / "*" / "SKILL.md")))
splunk_skill_paths = []

for skill_path in skill_paths:
    p = Path(skill_path)
    if "splunk" in str(p).lower():
        splunk_skill_paths.append(p)
        continue
    try:
        if "splunk" in p.read_text(encoding="utf-8").lower():
            splunk_skill_paths.append(p)
    except Exception:
        continue

for skill_path in project_skill_paths:
    p = Path(skill_path)
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        continue
    if "splunk" in str(p).lower() or "splunk" in text.lower() or "ai_lab" in text.lower():
        splunk_skill_paths.append(p)

print("SPLUNK-RELATED SKILLS — ~/.cursor/skills-cursor and project .cursor/skills:\n")
if not splunk_skill_paths:
    print("No Splunk-related skill files found.")
else:
    for p in splunk_skill_paths:
        print(f"## {p}\n")
        try:
            print(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Read error: {e}]")
        print("\n---\n")

print("OPERATIONAL REMINDERS:\n")
print("- Reset flow: stop backfill/live -> verify no orphan launcher/backfill/live -> stop Splunk -> clean spool -> remove indexes -> start Splunk")
print("- Mandatory gate after every reset: run bash scripts/test_smoke.sh before any generation or baseline/scenario tests")
print("- Preferred auth for scripted checks: token from ~/.cursor/mcp.json (mcpServers.splunk-mcp-server.env.AUTH_TOKEN)")
print("- Saved-search sync policy: full-copy local/savedsearches.conf -> default/savedsearches.conf; do not merge unless explicitly requested")
print("- Dashboard view sync (explicit user request only): full-copy local/data/ui/views/<view>.xml -> default/data/ui/views/<view>.xml (e.g. scenario_1_au.xml); Splunk uses local over default when both exist")
print("- Index intent: ran/fwa are reserved for other scenarios; alerts/episode are scheduled-search derived indexes")
print("- If user says scenario dashboard will be manually imported, do not propose dashboard design changes unless explicitly requested")
print("- Baseline script chain: test_baseline.sh -> test_backfill.sh (telemetry + TWAMP saved-search assertions; TWAMP minute-bucket limits: TWAMP_MINUTE_BUCKET_MIN / TWAMP_MINUTE_BUCKET_MAX)")
print("- TWAMP saved searches (app ai_lab): twamp_event_count_test, twamp_dmean_test, twamp_jmean_test (5m window in SPL; see default/savedsearches.conf)")
print("- TWAMP delay/jitter: shared slice noise × default.noise_stdev for integer wire cells (project_script_design.md); pps semantics for packet-rate fields")
print("- TWAMP UL sequence rule: next ul_firstpktSeq = previous ul_lastpktSeq + 1; no-loss check uses ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1")
print("- Scenario 1 focus: correlate TWAMP packet-loss behavior with cnc_interface_counter_json directional packet-rate gap behavior for VLAN 1002/1003")
PY
