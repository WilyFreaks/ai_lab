---
name: ai-lab-runtime-validation
description: Validate ai_lab baseline/live generation with saved-search-first checks.
---
# AI Lab Runtime Validation Skill

Use this skill when validating runtime generation behavior for `ai_lab`.

## Core policy

- Use saved searches in app `ai_lab` for app-level verification.
- Do not use ad-hoc/raw SPL unless the user explicitly asks for it.

## Saved searches

- `telemetry_if_counter_test`
- `interface_ifOutPktsRate_test`
- `interface_ifInPktsRate_test`
- `thousandeyes_response_time_sec_test`
- `srte_path_test`

## Time windows

- Reset-readiness checks (empty-state): all-time (`earliest_time=0`, `latest_time=now`).
- Live-generation checks: recent bounded window (recommended `-5m` to `now`).

## Runtime expectations

- `live_log.py` runs with a 1-minute scheduler tick.
- Per-source event generation follows effective interval gating (`minute % interval == 0`).
- With no active scenario, baseline values and baseline intervals apply.
- Restart continuity uses `baseline.live_last_tick_epoch` in `local/ai_lab_scenarios.conf`.
- For `cnc_srte_path_json`, output wire format follows sample extension (`sample.txt` -> `.txt` spool payload), while `props.conf`/`transforms.conf` must still break and parse per-event JSON correctly.
- `scenario_happening_probability` is per-source (`<index>#<sourcetype>#scenario_happening_probability`) and is evaluated in `live_log.py` during active scenario windows.

## Quick checklist

1. Run `scripts/reset_workshop_state.sh --yes`, then immediately run `scripts/test_smoke.sh` (mandatory reset gate).
2. Confirm generation gate is open (`region` locked, `baseline_generation_enabled=true`).
3. Confirm `backfill_start_time` exists and `live_last_tick_epoch` advances.
4. Run saved searches over `-5m` and verify non-zero recent data.
5. Run baseline quality tests via `scripts/test_baseline.sh`.

## SRTE-specific verification addendum

Use this when validating `index=telemetry sourcetype=cnc_srte_path_json`:

1. Confirm recent events exist in the last 5 minutes.
2. Confirm event separation is correct (no multi-object merge in a single event).
3. Confirm host metadata extraction works per event (`host` should reflect payload `vlan` values like `cnc_vlan1001..1004`).
4. During active `scenario_1`, confirm impacted VLAN path ratio behavior follows `telemetry#cnc_srte_path_json#scenario_happening_probability` in a recent window.

## Imported dashboard data-source audit

Use this when a dashboard XML is copied from another Splunk environment.

1. Extract all SPL data sources (`index=`, `sourcetype=`, `source=`, host filters, and explicit time windows).
2. Save an inventory CSV under `docs/` with columns:
   - `index,sourcetype,source,host,time duration`
3. Mark non-`ai_lab` dependencies (for example legacy indexes or external app script paths) as external dependencies.
4. Use the inventory as the source for a follow-up comparison CSV when mapping to `ai_lab` saved searches and indexes.

## Post-migration generation checkpoint

After data-source remapping in imported dashboards, validate that runtime data exists for the remapped streams before panel-level UI validation.

- Required stream checkpoint for current `scenario_1_au` migration:
  - `index=twamp`
  - `index=telemetry sourcetype=cnc_srte_path_json`
  - `index=telemetry sourcetype=cnc_interface_counter_json`
- If these streams are not present in a recent window, trigger generation first, then rerun validation.
