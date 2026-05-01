#!/usr/bin/env bash
python3 <<'PY'
import glob
from pathlib import Path

skills_root = Path.home() / ".cursor" / "skills-cursor"
skill_paths = sorted(glob.glob(str(skills_root / "*" / "SKILL.md")))
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

print("SPLUNK-RELATED SKILLS — ~/.cursor/skills-cursor:\n")
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
PY
