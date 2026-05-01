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
PY
