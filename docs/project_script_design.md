# Data Generation Script Design

## Overview

Three scripts under `bin/` handle all synthetic data generation for the workshop app.

```
bin/
├── launcher.py      # entry point, spawned by Splunk scripted input
├── backfill_log.py  # one-shot historical data generation
└── live_log.py      # continuous real-time data generation + scenario trigger
```

---

## launcher.py

**Invoked by:** `inputs.conf` scripted input at app startup.

**Responsibilities:**
1. Read `local/ai_lab_scenarios.conf` `[baseline]` stanza
2. Enforce generation gate before spawning workers:
   - `region` must be set to one of `au|jp`
   - `baseline_generation_enabled = true`
   - if gate is closed, exit safely (no worker spawn)
3. If gate is open and `backfill_start_time` is set to 0, or not set,
   - Set `backfill_start_time` to the current epoch time
   - Set `backfill_completed = false`
   - Write to `local/ai_lab_scenarios.conf`
4. Spawn `backfill_log.py` as a subprocess
5. Spawn `live_log.py` as a subprocess

---

## backfill_log.py

**Invoked by:** `launcher.py`

**Runs:** Once — exits when backfill is complete.

**Responsibilities:**
1. Read `backfill_start_time` and `backfill_days` from conf
2. If `backfill_completed = true`, exit immediately (already done)
3. Generate synthetic events at configured intervals for the window:
   `(backfill_start_time - backfill_days)` → `backfill_start_time`
4. Write generated events in bulk NDJSON files under app spool paths:
   - `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_metric/`
   - `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`
5. Ensure generated events include required metadata fields:
   - `index`
   - `sourcetype`
   - `source`
   - `host`
   - `timestamp`
5. Splunk file monitor stanzas in `default/inputs.conf` assign index/sourcetype on ingest
6. On completion, write `backfill_completed = true` to `local/ai_lab_scenarios.conf`

**Restart behavior:** 
If Splunk restarts mid-backfill, `backfill_start_time` is already set in `local/`, so the same time window is used.
In this case, scipts first need to check the latest timestamp of the events before starting synthetic event generation.
This is mandatory to avoid duplicate or missing data.

---

## live_log.py

**Invoked by:** `launcher.py`

**Runs:** Continuously until Splunk stops.

**Responsibilities:**
1. Read `backfill_start_time` from conf as the real-time anchor
2. Generate synthetic events at configured intervals and write to spool files for monitor ingestion
3. Read scenario runtime controls from `[scenarios]` in `local/ai_lab_scenarios.conf`
4. Treat `<scenario>_activated` as activation epoch (`0` means inactive)
5. Apply scenario overrides only during fault window:
   - start: `activated + fault_start * 60`
   - end: `start + fault_duration * 60`
6. Outside fault window, use baseline values

**Restart behavior:** 
If Splunk restarts and `backfill_start_time` is already set in `local/`, that indicates live_log.py needs to backfill the live events.
Check the latest timestamp of the events and backfill the events up to the current timestamp.
This is mandatory to avoid missing data.

---

## Production Data Quality Requirements

- Weekend/weekday transitions must be smooth in production generation logic.
- Do not introduce abrupt step changes at boundary hours (especially Sunday 22:00-23:59).
- Apply interpolation windows around Fri→Sat and Sun→Mon transitions so chart behavior stays realistic.

## Region Timezone Alignment (peak_rate_*)

`peak_rate_00` ... `peak_rate_23` must be evaluated using the local hour of the region selected in `workshop_introduction` (stored in `local/ai_lab_scenarios.conf` `[baseline] region`), not server-local time.

Scope:

- Applies to both `backfill_log.py` and `live_log.py`.
- Applies to all metrics that use hourly `peak_rate_*` curves.

Behavior:

- Same UTC timestamp may map to different `peak_rate_*` keys depending on selected region.
- Hour lookup for `peak_rate_<HH>` must use region-local wall-clock hour (`HH` in `00..23`).
- Region timezone mapping must be deterministic and shared by backfill/live logic.

Design intent:

- Workshop host selects region once in `workshop_introduction`.
- Synthetic daily seasonality then follows that region’s local business/overnight rhythm consistently in both historical and live generation.

---

## Ingestion Routing (inputs.conf monitors)

Scripted input launches `launcher.py` only. Event ingestion is file-based via monitor stanzas:

- `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_metric/`  
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:metric`
- `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_alerts/`  
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:alerts`
- `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`  
  → `index=telemetry`, `sourcetype=cnc_interface_counter_json`

**Derived `alerts` index:** there is no file-ingest `samples/...` path for `alerts` by design. The `alerts` index is populated by scheduled saved searches (workshop “alerting” materialization) rather than the NDJSON spool pipeline.

---

## State in local/ai_lab_scenarios.conf

```ini
```

- `local/ai_lab_scenarios.conf` is test-owned during workshop validation.
- Do not pre-populate or auto-mutate `local/` files from setup/migration steps.
- Initial local state should be blank (or keys absent) before workshop host actions.
- No python script to change `default/ai_lab_scenarios.conf`. Runtime change must be written in the local file.

## Required Runtime Scenarios

All scripts (`launcher.py`, `backfill_log.py`, `live_log.py`, and command scripts that write runtime state) must correctly handle both cases below:

1. **Workshop start with blank local config**
   - `local/ai_lab_scenarios.conf` may be empty or missing expected sections/options.
   - Scripts must create only the required local runtime keys when needed.
   - Missing values must be treated via fallback logic (no assumptions that keys already exist).

2. **Splunk restart after workshop has started**
   - Scripts must resume from local runtime state without data loss or duplicate generation.
   - `backfill_start_time` and completion markers must be reused to maintain timeline continuity.
   - If restart occurs mid-backfill or during live generation, scripts must reconcile with existing event timestamps before producing new events.

## Splunk Home Path Convention

- Scripts should use `SPLUNK_HOME` when provided.
- Default path convention for this project is Linux-style: `/opt/splunk`.
- Do not hardcode macOS-only paths such as `/Applications/Splunk` in project scripts.

## Scenario Activation Path

- Dashboard view (`scenario_control`) executes custom search command `scenariocontrol`.
- Command script `bin/scenario_control.py` writes scenario runtime values to `local/ai_lab_scenarios.conf`.
- Activation behavior:
  - Enable: set `<scenario>_activated` to current epoch time
  - Disable: set `<scenario>_activated` to `0`
