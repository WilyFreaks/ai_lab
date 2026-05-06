#!/usr/bin/env bash
python3 <<'PY'
import glob
from pathlib import Path

project_docs = sorted(glob.glob(str(Path.cwd() / "docs" / "project_*.md")))

print("PROJECT DESIGN DOCS — docs/project_*.md:\n")
if not project_docs:
    print("No docs/project_*.md files found.")
else:
    for doc_path in project_docs:
        p = Path(doc_path)
        print(f"## {p}\n")
        try:
            print(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Read error: {e}]")
        print("\n---\n")

print("RESUME AFTER A BREAK (see docs/project_ai_lab.md -> Resume after a break):")
print("- Reset -> mandatory bash scripts/test_smoke.sh; generation gate opens after workshop region lock + baseline_generation_enabled")
print("- local/ai_lab_scenarios.conf is runtime/test-owned; agent changes target default/ and docs only")
print("- live_log.py: scenario_happening_probability missing/invalid -> 1; no need to set telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability in [scenario_1] for full degradation each tick")
print("- TWAMP: *_lostperc 0-100 integer percent; UL sequence continuity; scenario_1 loss correlated with telemetry for VLAN 1002/1003")
print("- Restart workers or Splunk after generator/conf edits if processes were already running")
print("")
print("CURRENT IMPLEMENTATION FOCUS:")
print("- Scenario dashboards (e.g. scenario_1_au.xml): edit under local/data/ui/views/; on explicit request ('copy local dashboard to default') full-copy to default/data/ui/views/; Splunk prefers local at runtime when both exist")
print("- TWAMP baseline verification: saved searches twamp_event_count_test, twamp_dmean_test, twamp_jmean_test (default/savedsearches.conf; asserted in scripts/test_backfill.sh / test_baseline.sh)")
print("- TWAMP: shared per-slice noise for delay/jitter integer cells + pps packet-rate model; correlate with cnc_interface_counter_json in scenario_1 for VLANs 1002/1003")
print("- Scenario 1 telemetry reroute keys: telemetry#cnc_interface_counter_json#sample.json#reroute_from_slice / ...#reroute_to_slice / ...#reroute_pct / ...#reroute_start_minutes / ...#reroute_ramp_minutes")
print("- reroute_pct means conserved traffic shift from impacted slices to healthy slices (not independent +pct on healthy links)")
print("- Scenario 1 immediate R5->R7 gap keys: telemetry#cnc_interface_counter_json#sample.json#immediate_gap_out_key / ...#immediate_gap_in_key / ...#immediate_gap_pct")
print("- ThousandEyes response-time back-to-baseline keys: thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_start_minutes / ...back_to_baseline_ramp_minutes")
print("- ThousandEyes baseline abrupt-jump tolerance in scripts/test_backfill.sh uses TE_JUMP_OUTLIER_MIN / TE_JUMP_OUTLIER_MAX (default 0..2)")
print("- Baseline reroute path links (R8-R6, R6-R4, R4-R2) should use core-consistent traffic ranges")
print("- scenario_control.xml: region token bootstrap is XML-based via workshopregion action=status; link resolves as /app/ai_lab/scenario_1_$region$")
print("- scenariocontrol action=set: active=1 preserves existing non-zero <scenario>_activated; active=0 clears to 0")
PY
