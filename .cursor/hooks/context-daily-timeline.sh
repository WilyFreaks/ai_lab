#!/usr/bin/env bash
python3 <<'PY'
from pathlib import Path

timeline_path = Path.cwd() / "docs" / "daily_activity_timeline.md"
if timeline_path.exists():
    print("PROJECT RESUME CONTEXT — docs/daily_activity_timeline.md:\n")
    print(timeline_path.read_text(encoding="utf-8"))
else:
    print("PROJECT RESUME CONTEXT: docs/daily_activity_timeline.md not found.")
PY
