---
name: ai-lab-runtime-validation
description: Validate ai_lab baseline/live generation with saved-search-first checks.
---
# AI Lab Runtime Validation Skill

Use this skill when validating runtime generation behavior for `ai_lab`.

## When you return (short handoff)

Use this block when the operator is exhausted or returning after a long gap — **before** deep-diving code.

- Read **`docs/project_ai_lab.md`** → *Resume after a break* for paths, reset gate, and credentials pointers.
- If the user asks “where am I”, read **`docs/daily_activity_timeline.md`** first and report the latest **Resume anchor**.
- **`scenario_happening_probability`:** evaluated in **`live_log.py`** during active scenario windows; **omitted or invalid → 1**. **`[scenario_1]`** does **not** need `telemetry#cnc_service_health_json#scenario_happening_probability` for deterministic degraded service-health rows.
- **TWAMP:** `*_lostperc` = **0–100 integer percent**; rates = **pps**; correlate loss with `cnc_interface_counter_json` for VLAN **1002/1003** in `scenario_1`.
- **After reset:** `scripts/test_smoke.sh` is mandatory before other tests; **post-generation:** `scripts/test_baseline.sh` (not immediately after reset with empty indexes).
- Do **not** mutate **`local/`** from automation; treat as Splunk/test-owned.

## Core policy

- Use saved searches in app `ai_lab` for app-level verification.
- Do not use ad-hoc/raw SPL unless the user explicitly asks for it.
- Treat `local/savedsearches.conf` as the full source-of-truth set when the user asks to sync saved searches.
- Default sync behavior is full-copy replacement: copy `local/savedsearches.conf` to `default/savedsearches.conf`.
- Do not merge `local` and `default` saved-search stanzas unless the user explicitly asks for a merge.
- Respect manual dashboard-import ownership: if the user says they will manually import a dashboard source, do not propose dashboard design changes unless explicitly requested.

## Scenario dashboard XML (local → default)

- Scenario views (for example `scenario_1_au.xml`) are **edited under** `local/data/ui/views/` during workshop iteration.
- On explicit user request ("copy local dashboard to default", "sync scenario dashboard", "promote scenario XML local → default"), replace **`default/data/ui/views/<view>.xml`** with **`local/data/ui/views/<view>.xml`** via **full-file copy** (no merge). Optional: verify with `cmp` that files are byte-identical.
- **Splunk runtime:** when both files exist for the same view, **`local` wins**. `default/` is for repo and packaging; keep them in sync on request so what you ship matches what you authored.
- Do not overwrite `local/` from `default/` unless the user asks (opposite direction is rare). After copying to `default/`, reload the view in Splunk if the UI looks stale.

## Saved searches

- `telemetry_if_counter_test`
- `cnc_interface_ifOutPktsRate_test`
- `cnc_interface_ifInPktsRate_test`
- `thousandeyes_response_time_sec_test`
- `cnc_srte_path_test`
- `cnc_service_health_test`
- `twamp_event_count_test`
- `twamp_dmean_test`
- `twamp_jmean_test`

## TWAMP saved searches (baseline verification)

Shipped in `default/savedsearches.conf` and asserted by `scripts/test_backfill.sh` (same checks run via `scripts/test_baseline.sh`):

| Saved search | Role |
|--------------|------|
| `twamp_event_count_test` | Last 5m: `bin span=1m _time` then count of minute buckets with ≥1 TWAMP event (`minute_buckets_with_data`). Nominal ~5; partial clock edges may yield fewer; script default range `3–6` unless overridden by `TWAMP_MINUTE_BUCKET_MIN` / `TWAMP_MINUTE_BUCKET_MAX`. |
| `twamp_dmean_test` | Last 5m: averages indexed `ul_dmean*`, `dl_dmean*`, `rt_dmean*` by direction; script checks each against aggregated `daily_min`/`daily_max` for `twamp#pca_twamp_csv#slice*_{ul|dl|rt}_dmean` plus noise tolerance. |
| `twamp_jmean_test` | Same pattern for `*_jmean` fields vs conf keys `slice*_{ul|dl|rt}_jmean`. |

Duplicate CSV header columns (`ul_dmean`, `ul_dmean1`, …) are selected with wildcards in SPL.

## Time windows

- Reset-readiness checks (empty-state): all-time (`earliest_time=0`, `latest_time=now`).
- Live-generation checks: recent bounded window (recommended `-5m` to `now`).

## Runtime expectations

- `live_log.py` runs with a 1-minute scheduler tick.
- Per-source event generation follows effective interval gating (`minute % interval == 0`).
- Optional `<<index>#<sourcetype>#event_interval_sec` subdivides an eligible tick into multiple events (spaced in seconds); see `samples/twamp/pca_twamp_csv/README.md` and `docs/project_script_design.md`.
- With no active scenario, baseline values and baseline intervals apply.
- Restart continuity uses `baseline.live_last_tick_epoch` in `local/ai_lab_scenarios.conf`.
- For `cnc_srte_path_json`, output wire format follows sample extension (`sample.txt` -> `.txt` spool payload), while `props.conf`/`transforms.conf` must still break and parse per-event JSON correctly.
- `scenario_happening_probability` is per-source (`<index>#<sourcetype>#scenario_happening_probability`) and is evaluated in `live_log.py` during active scenario windows.
- For TWAMP CSV (`pca_twamp_csv`), treat packet-rate fields as packets per second (pps) unless the user explicitly asks for a different unit model.
- TWAMP delay/jitter integers still **fluctuate across ticks**: one standard-normal draw **per slice per event** scales `twamp#pca_twamp_csv#default.noise_stdev` for all noisy delay/jitter fields in that slice (see `docs/project_script_design.md`).
- TWAMP UL packet sequence continuity is mandatory across backfill/live/restart:
  - `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
  - no-loss check: `ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
- During `scenario_1`, TWAMP loss for **slice1002/slice1003** uses **`[scenario_1]`** `*_rxpkts_drop_rate = 0.3` (**ul/dl/rt**); generators derive `*_lostpkts` and `*_lostperc` (integer **percent 0–100**) from expected vs received counts so packet-loss columns align with `cnc_interface_counter_json` gap behavior for VLANs 1002/1003.
- Index intent:
  - `ran`/`fwa` are reserved for other scenarios.
  - `alerts`/`episode` are derived from scheduled searches (not direct generator streams).

## Quick checklist

1. Run `scripts/reset_workshop_state.sh --yes`, then immediately run `scripts/test_smoke.sh` (mandatory reset gate).
2. Confirm generation gate is open (`region` locked, `baseline_generation_enabled=true`).
3. Confirm `backfill_start_time` exists and `live_last_tick_epoch` advances.
4. Run saved searches over `-5m` and verify non-zero recent data (including `index=twamp` when TWAMP is in scope).
5. Run baseline quality tests via `scripts/test_baseline.sh` (includes TWAMP `twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test` via `test_backfill.sh`).
6. For TWAMP + telemetry scenario checks, validate in a recent window that TWAMP UL loss indicators and telemetry directional in/out packet gaps move together for VLAN 1002/1003 during `scenario_1`.

## SRTE-specific verification addendum

Use this when validating `index=telemetry sourcetype=cnc_srte_path_json`:

1. Confirm recent events exist in the last 5 minutes.
2. Confirm event separation is correct (no multi-object merge in a single event).
3. Confirm host metadata extraction works per event (`host` should reflect payload `vlan` values like `cnc_vlan1001..1004`).
4. During active `scenario_1`, confirm impacted VLAN path ratio behavior follows `telemetry#cnc_srte_path_json#scenario_happening_probability` in a recent window.

## Service health verification addendum

Use this when validating `index=telemetry sourcetype=cnc_service_health_json` during **`scenario_1`**:

1. Omit **`telemetry#cnc_service_health_json#scenario_happening_probability`** in **`[scenario_1]`** unless you want stochastic baseline fallback: when missing or invalid, **`live_log.py`** defaults it to **`1`**, so degraded **`impacted_sre_policy_health_status`** / **`impacted_sr_policy_health_score`** apply on every eligible emission (see `docs/project_scenario_1.md` and `samples/telemetry/cnc_service_health_json/README.md`).
2. In a recent window with scenario active, confirm VLAN 1002/1003 **sr_policy** rows show **`SERVICE_DEGRADED`** / **50** (via dashboard or `cnc_service_health_test` / saved-search contract).

## Scenario control dashboard addendum

Use this when validating `default/data/ui/views/scenario_control.xml` and `bin/scenario_control.py` behavior.

1. Dashboard load should set `region` from `| workshopregion action="status"` (XML `search/done` path), and the monitoring link should resolve as `/app/ai_lab/scenario_1_$region$`.
2. Opening `scenario_control` must **not** mutate `<scenario>_activated` by itself (no write on load).
3. Submit-driven write path uses `| scenariocontrol action=set ...` with submitted tokens only.
4. `active=1` on an already-active scenario must preserve existing non-zero `<scenario>_activated` (no timestamp reset on repeated enable).
5. `active=0` must clear `<scenario>_activated` to `0`.

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
