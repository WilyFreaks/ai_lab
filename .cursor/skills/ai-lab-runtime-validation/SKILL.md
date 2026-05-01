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

## Time windows

- Reset-readiness checks (empty-state): all-time (`earliest_time=0`, `latest_time=now`).
- Live-generation checks: recent bounded window (recommended `-5m` to `now`).

## Runtime expectations

- `live_log.py` runs with a 1-minute scheduler tick.
- Per-source event generation follows effective interval gating (`minute % interval == 0`).
- With no active scenario, baseline values and baseline intervals apply.
- Restart continuity uses `baseline.live_last_tick_epoch` in `local/ai_lab_scenarios.conf`.

## Quick checklist

1. Confirm generation gate is open (`region` locked, `baseline_generation_enabled=true`).
2. Confirm `backfill_start_time` exists and `live_last_tick_epoch` advances.
3. Run saved searches over `-5m` and verify non-zero recent data.
4. Run baseline quality tests via `scripts/test_baseline.sh`.
