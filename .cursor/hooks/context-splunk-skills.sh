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

print("RESUME AFTER A BREAK (human-tired / long gap):\n")
print("- Read docs/project_ai_lab.md -> section 'Resume after a break' before touching generators or Splunk")
print("- 'Where am I?': read docs/daily_activity_timeline.md first; do not proactively edit it unless user asks")
print("- scenario_happening_probability: live_log.py default 1.0 when missing; omit redundant =1 for telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability in [scenario_1]")
print("- TWAMP *_lostperc: integer percent 0-100 on the wire; packet-rate fields = pps")
print("- After changing bin/*.py or default/ai_lab_scenarios.conf: restart live_log/backfill or Splunk if workers already running")
print("\nOPERATIONAL REMINDERS:\n")
print("- Reset flow: stop backfill/live -> verify no orphan launcher/backfill/live -> stop Splunk -> clean spool -> remove indexes -> start Splunk")
print("- Mandatory gate after every reset: run bash scripts/test_smoke.sh before any generation or baseline/scenario tests")
print("- Smoke/reset: treat ai_lab_logs as empty only when excluding sourcetypes ai_lab:launcher, ai_lab:spool_cleanup")
print("- test_backfill.sh implements baseline quality + optional backfill/live ingest handoff checks; test_baseline.sh is a thin wrapper (exec)")
print("- Preferred auth for scripted checks: token from ~/.cursor/mcp.json (mcpServers.splunk-mcp-server.env.AUTH_TOKEN)")
print("- Saved-search sync policy: full-copy local/savedsearches.conf -> default/savedsearches.conf; do not merge unless explicitly requested (includes alert scheduled searches targeting index=alerts)")
print("- Telemetry ifIn/ifOut on opposite ends of a physical link share one daily_variation draw; backfill_log.py and live_log.py must stay in parity for helper code")
print("- Dashboard view sync (explicit user request only): full-copy local/data/ui/views/<view>.xml -> default/data/ui/views/<view>.xml (e.g. scenario_1_au.xml); Splunk uses local over default when both exist")
print("- Index intent: ran/fwa are reserved for other scenarios; alerts/episode are scheduled-search derived indexes")
print("- If user says scenario dashboard will be manually imported, do not propose dashboard design changes unless explicitly requested")
print("- Baseline script chain: test_baseline.sh -> test_backfill.sh (telemetry + TWAMP saved-search assertions; TWAMP minute-bucket limits: TWAMP_MINUTE_BUCKET_MIN / TWAMP_MINUTE_BUCKET_MAX)")
print("- TWAMP saved searches (app ai_lab): twamp_event_count, twamp_dmean, twamp_jmean (5m window in SPL; see default/savedsearches.conf)")
print("- TWAMP delay/jitter: shared slice noise × twamp#pca_twamp_csv#sample.csv#default.noise_stdev for integer wire cells (project_script_design.md); pps semantics for packet-rate fields")
print("- TWAMP UL sequence rule: next ul_firstpktSeq = previous ul_lastpktSeq + 1; no-loss check uses ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1")
print("- TWAMP *_lostperc wire scale: integer percent 0-100 (lost vs expected), not millionths")
print("- Scenario 1 focus: correlate TWAMP packet-loss behavior with cnc_interface_counter_json directional packet-rate gap behavior for VLAN 1002/1003")
print("- Scenario 1 telemetry reroute keys: telemetry#cnc_interface_counter_json#sample.json#reroute_from_slice, ...#reroute_to_slice, ...#reroute_pct, ...#reroute_start_minutes, ...#reroute_ramp_minutes")
print("- reroute_pct semantics: conserved shift (remove from impacted slices, redistribute to healthy slices), not independent +pct on healthy links")
print("- Immediate R5->R7 gap keys: telemetry#cnc_interface_counter_json#sample.json#immediate_gap_out_key / ...#immediate_gap_in_key / ...#immediate_gap_pct")
print("- ThousandEyes response-time recovery keys: thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_start_minutes + ...back_to_baseline_ramp_minutes")
print("- Syslog WDM issue source: wdm_alert XML with host extracted from NativeEMSName alias-value")
print("- WDM PM mapping source: lookups/router_wdm_transponders.csv (A/Z endpoints + bound transponder ports)")
print("- Scenario one-shot emit-state must be per scenario+stream so IOS BFD and WDM alert both fire once for the same activation")
print("- Baseline reroute path links (R8-R6, R6-R4, R4-R2) must stay core-consistent range, not single-digit outliers")
print("- Scenario 1 service health: omit `telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability` in `[scenario_1]` unless you want stochastic baseline fallback; missing key defaults to 1 (see `docs/project_scenario_1.md`)")
print("- ThousandEyes baseline abrupt-jump allowance in scripts/test_backfill.sh: TE_JUMP_OUTLIER_MIN / TE_JUMP_OUTLIER_MAX (default 0..2)")
print("- scenario_control.xml: bootstrap region token via XML search (`workshopregion action=status`); dashboard link uses /app/ai_lab/scenario_1_$region$")
print("- scenariocontrol command: repeated Enable must not overwrite non-zero <scenario>_activated; Disable sets it to 0")
print("- Spool cleanup: bin/spool_cleanup.py runs hourly via scripted input (interval=3600 in default/inputs.conf); deletes var/spool/ai_lab/ files older than 4h; preserves directory structure; emits JSON to index=ai_lab_logs sourcetype=ai_lab:spool_cleanup; activated by Splunk restart; do not lower 4h threshold below longest monitor polling cycle")
PY
