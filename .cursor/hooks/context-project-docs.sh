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

print("CURRENT IMPLEMENTATION FOCUS:")
print("- Scenario dashboards (e.g. scenario_1_au.xml): edit under local/data/ui/views/; on explicit request ('copy local dashboard to default') full-copy to default/data/ui/views/; Splunk prefers local at runtime when both exist")
print("- TWAMP baseline verification: saved searches twamp_event_count_test, twamp_dmean_test, twamp_jmean_test (default/savedsearches.conf; asserted in scripts/test_backfill.sh / test_baseline.sh)")
print("- TWAMP: shared per-slice noise for delay/jitter integer cells + pps packet-rate model; correlate with cnc_interface_counter_json in scenario_1 for VLANs 1002/1003")
PY
