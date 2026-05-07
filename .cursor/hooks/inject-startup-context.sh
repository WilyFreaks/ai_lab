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
    "Instruction: Use the resume anchor from the timeline and align all work with the project design docs and Splunk skill guidance. Apply saved-search sync as full-copy local->default unless merge is explicitly requested, avoid unsolicited scenario-dashboard design changes when user says import is manual, keep wdm_alert/wdm_pm source contracts aligned with lookups + props/transforms docs, and preserve per-scenario+stream one-shot emission behavior (no cross-stream suppression)."
)

python3 -c 'import json,sys; print(json.dumps({"additional_context": sys.stdin.read()}))' <<< "$combined"
