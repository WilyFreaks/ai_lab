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

**Resume after a break:** Ordering and gates → `docs/project_ai_lab.md` → *Handoff* → *Resume after a break*. Never run **`scripts/test_baseline.sh`** on an empty workshop right after reset; run **`scripts/test_smoke.sh`** first, then open the generation gate, then baseline tests.

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

1. **Reset must be followed by smoke (mandatory)**:
   - every run of `scripts/reset_workshop_state.sh` must be followed immediately by `scripts/test_smoke.sh`
   - this is the required gate before any further test flow
2. **Reset-phase checks** (`scripts/test_smoke.sh`) are meaningful immediately after reset/start and must pass with empty indexes (clean slate ready to start workshop).
3. **Generation gate must be opened before post-generation tests**:
   - after reset, generation is still gated (`baseline_generation_enabled=false` until region lock path runs)
   - you must lock/select region first (for example via Workshop Introduction Submit, or `| workshopregion action="set" region="<au|jp>"`)
   - only after this step should `backfill_log.py`/`live_log.py` populate datasets
4. **Post-generation quality checks** (`scripts/test_baseline.sh`) are meaningful only after generation has started and saved-search datasets are populated. This entrypoint runs `scripts/test_backfill.sh`, including TWAMP assertions (`twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test`); optional env `TWAMP_MINUTE_BUCKET_MIN` / `TWAMP_MINUTE_BUCKET_MAX` adjusts the minute-bucket expectation for `twamp_event_count_test`.
5. **Scenario checks** (`scripts/test_scenario_1.sh`) are meaningful **only after** generation/scenario data exists.
6. Running post-generation or scenario checks on empty indexes can return trivial zero rows (for example “No matching fields exist”), which is not a valid data-quality pass.

Contract clarification:

- `scripts/test_smoke.sh` is a **post-reset readiness** test (empty-state contract), and must be run immediately after every workshop reset.
- `scripts/test_baseline.sh` is a **post-generation data-quality** test (expects saved searches to return data and validates quality constraints); do not run it immediately after reset before region lock.
- `scripts/test_backfill.sh` is a **historical backfill coverage + quality** test (head/tail window coverage plus saved-search quality checks); do not run it immediately after reset before region lock.
- Saved-search packaging sync policy: when promoting runtime search definitions, copy `local/savedsearches.conf` to `default/savedsearches.conf` as full replacement unless an explicit merge is requested.
- Scenario dashboard XML sync (on explicit request): copy `local/data/ui/views/<view>.xml` to `default/data/ui/views/<view>.xml` as a full-file replacement (`cp`); no merge. Splunk resolves the same view name with **`local` over `default`**, so functional UI state follows `local/` when both exist—sync to `default/` for repo/AMI parity and documentation.

Saved-search contract for baseline/live verification:

- App context: run saved searches in `ai_lab`.
- Naming convention: use `cnc_`-prefixed saved-search names for interface/SRTE/service-health baseline checks.
- Required saved searches:
  - `telemetry_if_counter_test`
  - `cnc_interface_ifOutPktsRate_test`
  - `cnc_interface_ifInPktsRate_test`
  - `thousandeyes_response_time_sec_test`
  - `cnc_srte_path_test`
  - `cnc_service_health_test`
  - `twamp_event_count_test`
  - `twamp_dmean_test`
  - `twamp_jmean_test`
- Live verification window:
  - use a recent bounded window (recommended `earliest=-5m latest=now`) when confirming active `live_log.py` generation.

Saved-search quality intent for backfill checks:

- `telemetry_if_counter_test`:
  - directional gap must never be negative
  - drop rate must never exceed `1`
- `cnc_srte_path_test`:
  - must return non-zero results when `cnc_srte_path_json` generation is active
- `cnc_service_health_test`:
  - must return non-zero results when generation is active; during **`scenario_1`**, **`impacted_sre_policy_health_status`** / score overrides apply each tick because **`scenario_happening_probability` defaults to 1** when omitted (validate in UI or ad-hoc recent-window spot-check if extending tests)
- `cnc_interface_ifInPktsRate_test`, `cnc_interface_ifOutPktsRate_test`, `thousandeyes_response_time_sec_test`:
  - generated values must stay in the configured range from `default/ai_lab_scenarios.conf`
  - values should fluctuate gradually, unless an explicitly activated scenario fault window expects abrupt change
- `twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test` (see `scripts/test_backfill.sh`):
  - minute buckets with TWAMP events in the last 5 minutes (nominal ~5; partial-window edges may be lower)
  - average `ul`/`dl`/`rt` `dmean` and `jmean` within aggregated `daily_min`/`daily_max` from `default/ai_lab_scenarios.conf`, with tolerance from per-metric or default TWAMP `noise_stdev`

---

## Dashboard-Specific Tests

### workshop_introduction

- On load, JS dispatches `| workshopregion action="status"` (no baseline Simple XML search).
- If `region_ready=false`: fieldset (dropdown + Submit) visible, save row hidden.
- If `region_ready=true`: fieldset + description hidden by JS; backfill status panel visible.
- After save (Submit clicked): `<done>` sets `region_locked=true`, transitions to locked state.
- Dashboard default navigation lands on this view.

### scenario_control

- Region bootstrap search (`workshopregion action="status"`) sets `region` token on load for dynamic dashboard link resolution.
- Opening the dashboard must not mutate `<scenario>_activated`.
- Submit updates local scenario control keys via `scenariocontrol action=set`.
- Repeated **Enable** submit while already active must preserve existing non-zero `<scenario>_activated` value.
- **Disable** submit must set `<scenario>_activated=0`.
- Defaults and help text are rendered as intended.

### Imported dashboards (copied from other environments)

- Before migration/refactor, create a source-inventory CSV in `docs/` with columns:
  - `index,sourcetype,source,host,time duration`
- Explicitly flag any non-`ai_lab` index usage and external app script paths as external dependencies.
- Use the inventory CSV as the baseline for a comparison list when remapping panels to `ai_lab` saved searches.
- After remapping imported dashboard panels, execute a generation checkpoint for remapped streams before UI-level dashboard validation.
- Current `scenario_1_au` checkpoint streams:
  - `index=twamp`
  - `index=telemetry sourcetype=cnc_srte_path_json`
  - `index=telemetry sourcetype=cnc_interface_counter_json`

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

1. stop app generator workers (`backfill_log.py`, `live_log.py`)
2. confirm no orphan `launcher.py` / `backfill_log.py` / `live_log.py` process remains
3. stop Splunk
4. delete monitored spool files under the app:
   - `$SPLUNK_HOME/etc/apps/ai_lab/var/spool/ai_lab`
5. delete app index data (directory tree and matching `<index>.dat` metadata, where present)
6. delete `local/ai_lab_scenarios.conf`
7. start Splunk
8. mandatory immediate smoke gate:
   - run `bash scripts/test_smoke.sh` and require pass before generation tests
9. optional verification pass:
   - `index=<app_index> earliest=0 latest=now | stats count` must be 0 (supports token auth via `SPLUNK_TOKEN`)

Conventions and safety:

- Uses `SPLUNK_HOME` when set; defaults to `/opt/splunk`. On **macOS** developer machines, set `SPLUNK_HOME` to the real install, e.g. `export SPLUNK_HOME=/Applications/Splunk`, before running.
- Index targets are derived from `default/indexes.conf` (no hardcoded index list).
- Script validates index names and refuses unsafe delete targets.
- Script validates resolved delete path remains under `$SPLUNK_DB`.
- Supports interactive confirm and non-interactive mode (`--yes`).
- Post-start verification should prefer `SPLUNK_TOKEN` (or `AUTH_TOKEN`) from Cursor MCP config, and support `SPLUNK_AUTH` only as fallback.
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

