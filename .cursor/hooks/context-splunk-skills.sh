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
PY
