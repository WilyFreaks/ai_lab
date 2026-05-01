#!/usr/bin/env bash
set -euo pipefail

timeline_block=$(bash .cursor/hooks/context-daily-timeline.sh)
skills_block=$(bash .cursor/hooks/context-splunk-skills.sh)
docs_block=$(bash .cursor/hooks/context-project-docs.sh)

combined=$(
  printf "%s\n\n====================\n\n%s\n\n====================\n\n%s\n\n====================\n\n%s\n" \
    "$timeline_block" \
    "$skills_block" \
    "$docs_block" \
    "Instruction: Use the resume anchor from the timeline and align all work with the project design docs and Splunk skill guidance."
)

python3 -c 'import json,sys; print(json.dumps({"additional_context": sys.stdin.read()}))' <<< "$combined"
