---
name: Test Design Decisions
description: Test strategy and automation contract for ai_lab dashboards, commands, and data generators
type: project
originSessionId: 023ba004-a2ab-41d3-9152-4eb0746bfa20
---
# Test Design

## Overview

This document defines how `ai_lab` is tested during iterative development and workshop validation.

Primary goals:

1. Verify dashboards and custom commands behave correctly.
2. Verify synthetic event generation and ingestion routing.
3. Make test execution repeatable so Cursor can run checks automatically.

---

## Test Scope

Test scope includes:

- Dashboard behavior:
  - `workshop_introduction`
  - `scenario_control`
- Custom commands:
  - `workshopregion`
  - `scenariocontrol`
- Generator scripts:
  - `bin/launcher.py`
  - `bin/backfill_log.py`
  - `bin/live_log.py`
- Ingestion routing:
  - `default/inputs.conf` monitor stanzas
  - target indexes/sourcetypes

Out of scope:

- Splunk platform internals not controlled by app config
- Performance benchmarking at production scale

---

## Core Test Principles

- Keep `local/` test-owned.
- Do not mutate `default/` at runtime.
- Prefer deterministic, scriptable checks over manual inspection.
- Use one canonical test entrypoint so both humans and Cursor run the same flow.

---

## Canonical Test Contract

The repository should expose one command as the test contract:

```bash
bash tests/smoke/test_smoke.sh
```

This command should return:

- exit `0`: all required checks passed
- non-zero: failure (must include actionable error output)

Recommended layout:

- `tests/smoke/test_smoke.sh`
- `tests/splunk/run_spl_checks.sh`
- `tests/README.md`

The smoke script should orchestrate:

1. static/syntax checks for Python files
2. runtime precondition checks (required config/paths)
3. Splunk SPL assertions for ingestion and control behavior
4. hard precondition that app indexes are empty before scenario execution

---

## Required Runtime Scenarios

All tests must cover these two mandatory scenarios:

1. **Blank local start**
   - `local/ai_lab_scenarios.conf` is empty or missing keys.
   - Dashboard should allow initial region selection.
   - Generation should start only after explicit host action.

2. **Restart continuity**
   - Splunk restarts after workshop has started.
   - Scripts must resume using local runtime state.
   - No duplicate window replay and no missing timeline gap.

---

## SPL Validation Matrix

Minimum SPL assertions for smoke pass:

1. All app indexes from `default/indexes.conf` are empty:
   - `index=<app_index> | stats count`
2. If `alerts` is present in `default/indexes.conf`, it is part of the same “empty pre-run” contract:
   - it may legitimately be empty in a clean workshop (scheduled searches have not materialized output yet)
3. If `episode` is present, it is also part of the same “empty pre-run” contract:
   - it is derived from `alerts` and may be empty if no alerts exist yet, or if the materialization job has not run
4. No parser/format failures for generated payloads:
   - check `_internal` for relevant parsing errors.

Execution rules:

- Use full historical range when validating empty state (`earliest_time=0`, `latest_time=now`).
- Do not prefix SPL with `search` in these script checks; use implicit search form:
  - `index=telemetry | stats count`
  - not `search index=telemetry | stats count`

Recommended additional assertions:

- `backfill_completed` transition in local state after backfill run
- region lock/unlock behavior in `workshop_introduction`
- scenario activation write path in `scenariocontrol`

---

## Dashboard-Specific Tests

### workshop_introduction

- If region is not set in local, region selector is available.
- After save, selected region is shown and selector is locked.
- Dashboard default navigation lands on this view.

### scenario_control

- Search runs only on submit.
- Submit updates local scenario control keys.
- Defaults and help text are rendered as intended.

---

## Data Generation Tests

### backfill_log.py

- Uses `backfill_days` to compute historical window.
- Writes NDJSON outputs to configured spool paths.
- Each NDJSON line should match the sample template in `samples/.../sample.json` (only add keys the template/README authorizes). Splunk routing metadata comes from `default/inputs.conf` monitors, not from extra JSON fields.
- Marks `backfill_completed=true` on success.

### live_log.py

- Runs continuously once implemented.
- Uses same region-timezone `peak_rate_*` mapping as backfill.
- Applies scenario fault window overrides correctly.

---

## Cursor Automation Integration

To allow automatic test execution by Cursor:

1. Keep canonical command stable:
   - `bash tests/smoke/test_smoke.sh`
2. Document it in `.cursor/rules/splunk_app_rules.md`.
3. Ensure scripts are non-interactive and produce clear pass/fail output.

This keeps test behavior consistent across manual and agent-driven runs.

Transport/auth for scripted tests:

- `tests/splunk/run_spl_checks.sh` uses local Splunk CLI auth (`-auth "$SPLUNK_AUTH"`).
- MCP token-based query execution is intentionally not used for test scripts.

---

## Environment Reset Script

Repository reset helper:

- `scripts/reset_workshop_state.sh`

Purpose:

1. stop Splunk
2. delete app index data (directory tree and matching `<index>.dat` metadata, where present)
3. delete monitored spool files under the app:
   - `$SPLUNK_HOME/etc/apps/ai_lab/var/spool/ai_lab`
4. delete `local/ai_lab_scenarios.conf`
5. start Splunk
6. optional verification pass:
   - `index=<app_index> earliest=0 latest=now | stats count` must be 0 (requires `SPLUNK_AUTH`)

Conventions and safety:

- Uses `SPLUNK_HOME` when set; defaults to `/opt/splunk`. On **macOS** developer machines, set `SPLUNK_HOME` to the real install, e.g. `export SPLUNK_HOME=/Applications/Splunk`, before running.
- Index targets are derived from `default/indexes.conf` (no hardcoded index list).
- Script validates index names and refuses unsafe delete targets.
- Script validates resolved delete path remains under `$SPLUNK_DB`.
- Supports interactive confirm and non-interactive mode (`--yes`).
- Post-start verification **requires** `SPLUNK_AUTH` (e.g. `export SPLUNK_AUTH=admin:…`); the script exits non-zero if verification is required but auth is not set. Workshop password used in local docs: see `docs/project_ai_lab.md`.
- Operator checklist and “next session” pointers: `docs/project_ai_lab.md` → *Handoff: operators and the next implementer*.

---

## Failure Reporting Standard

Test scripts should print:

- failed check name
- command or SPL used
- observed value vs expected value
- suggested next debug step

This is required so failures can be fixed quickly in chat without manual triage.

---

## Source of Truth Boundaries

To keep documentation maintainable:

- Project/app runtime decisions are documented in project files under `docs/`.
- Splunk SPL authoring and review conventions are documented in the Cursor skill:
  - `~/.cursor/skills-cursor/splunk-search-assistant/SKILL.md`
- Test behavior and pass/fail contract remain in this file and `tests/README.md`.

Project files should capture app-specific behavior (runtime state model, test contract, restart behavior), while SPL syntax/style policy should be maintained in the Splunk skill.

