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

The repository exposes one canonical command as the test contract:

```bash
bash scripts/test_smoke.sh
```

This command should return:

- exit `0`: all required checks passed
- non-zero: failure (must include actionable error output)

Current layout:

- `scripts/test_smoke.sh`
- `scripts/test_baseline.sh`
- `scripts/test_scenario_1.sh`
- `scripts/test_backfill.sh` (backfill-focused historical-window coverage checks; used by baseline wrapper)

The smoke script should orchestrate:

1. static/syntax checks for Python files
2. runtime precondition checks (required config/paths)
3. spool directory emptiness check (`var/spool/ai_lab`)
4. Splunk SPL assertions for **reset-ready state** (all app indexes empty)

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

Minimum assertions for smoke pass (4 checks, all must pass):

1. Python syntax: `py_compile` on all `bin/*.py` files
2. Runtime preconditions: required files/paths/auth present
3. Spool directory empty: `var/spool/ai_lab` contains 0 files
4. All app indexes from `default/indexes.conf` are empty:
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

Execution sequencing (important):

1. **Reset-phase checks** (`scripts/test_smoke.sh`) are meaningful immediately after reset/start and must pass with empty indexes (clean slate ready to start workshop).
2. **Post-generation quality checks** (`scripts/test_baseline.sh`) are meaningful only after generation has started and saved-search datasets are populated.
3. **Scenario checks** (`scripts/test_scenario_1.sh`) are meaningful **only after** generation/scenario data exists.
4. Running post-generation or scenario checks on empty indexes can return trivial zero rows (for example “No matching fields exist”), which is not a valid data-quality pass.

Contract clarification:

- `scripts/test_smoke.sh` is a **post-reset readiness** test (empty-state contract).
- `scripts/test_baseline.sh` is a **post-generation data-quality** test (expects saved searches to return data and validates quality constraints).
- `scripts/test_backfill.sh` is a **historical backfill coverage + quality** test (head/tail window coverage plus saved-search quality checks).

Saved-search contract for baseline/live verification:

- App context: run saved searches in `ai_lab`.
- Required saved searches:
  - `telemetry_if_counter_test`
  - `interface_ifOutPktsRate_test`
  - `interface_ifInPktsRate_test`
  - `thousandeyes_response_time_sec_test`
- Live verification window:
  - use a recent bounded window (recommended `earliest=-5m latest=now`) when confirming active `live_log.py` generation.

Saved-search quality intent for backfill checks:

- `telemetry_if_counter_test`:
  - directional gap must never be negative
  - drop rate must never exceed `1`
- `interface_ifInPktsRate_test`, `interface_ifOutPktsRate_test`, `thousandeyes_response_time_sec_test`:
  - generated values must stay in the configured range from `default/ai_lab_scenarios.conf`
  - values should fluctuate gradually, unless an explicitly activated scenario fault window expects abrupt change

---

## Dashboard-Specific Tests

### workshop_introduction

- On load, JS dispatches `| workshopregion action="status"` (no baseline Simple XML search).
- If `region_ready=false`: fieldset (dropdown + Submit) visible, save row hidden.
- If `region_ready=true`: fieldset + description hidden by JS; backfill status panel visible.
- After save (Submit clicked): `<done>` sets `region_locked=true`, transitions to locked state.
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
- Uses 1-minute orchestrator ticks and per-source interval gating (`minute % interval == 0`).
- Persists and resumes minute cursor (`baseline.live_last_tick_epoch`) for restart continuity.

---

## Cursor Automation Integration

To allow automatic test execution by Cursor:

1. Keep canonical command stable:
   - `bash scripts/test_smoke.sh`
2. Document it in `.cursor/rules/splunk_app_rules.mdc`.
3. Ensure scripts are non-interactive and produce clear pass/fail output.

This keeps test behavior consistent across manual and agent-driven runs.

Transport/auth for scripted tests:

- Auth transport for scripted tests should support either local CLI auth (`-auth "$SPLUNK_AUTH"`) or token auth (`-token "$SPLUNK_TOKEN"`).

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
- Test behavior and pass/fail contract remain in this file and the scripts under `scripts/`.

Project files should capture app-specific behavior (runtime state model, test contract, restart behavior), while SPL syntax/style policy should be maintained in the Splunk skill.

