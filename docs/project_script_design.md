# Data Generation Script Design

## Overview

Three scripts under `bin/` handle all synthetic data generation for the workshop app.

```
bin/
├── launcher.py      # entry point, spawned by Splunk scripted input
├── backfill_log.py  # one-shot historical data generation
└── live_log.py      # continuous real-time data generation + scenario trigger
```

## Domain timestamps (`{{timestamp}}`) — IANA + ISO-8601

Workshop data should treat timestamps as a **first-class, timezone-explicit** domain clock (not “Splunk’s indexer local time by accident”).

**Target wire format (what we want the JSON to contain):** ISO-8601 **with a numeric offset**, including fractional seconds if needed, for example:

- `2026-04-26T17:09:25.034+09:00`

**Region → IANA zone (authoritative for offsets and DST):**

- `jp` → `Asia/Tokyo` (effectively a stable `+09:00` in normal operation; no DST)
- `au` → `Australia/Sydney` (DST-aware; offset is typically `+10:00` or `+11:00` depending on the instant)

**How to compute it (principle, not a manual calendar):**

- Use the Python runtime’s `zoneinfo` data for the selected IANA zone (this follows the **IANA time zone database** rules shipped with the runtime).
- Do **not** hand-maintain “season boundaries” in workshop code. If civil-time rules change, the fix is **updating the runtime’s tzdata** (and redeploying), not inventing new switch dates in generators.

**Splunk alignment requirement:**

- `default/props.conf` `TIME_FORMAT` for each `sourcetype` must match the exact `{{timestamp}}` string shape, so `_time` lines up with the domain timestamp in the JSON.

**Status note (engineering reality check):** treat the above as the **target contract**. If the current generator and `props.conf` in git still use an older string shape, the next work session should make them **match exactly** (generator + `TIME_FORMAT` + sample templates), then re-generate spool data for validation.

---

## launcher.py

**Invoked by:**
- `inputs.conf` scripted input at app startup
  - Purpose: auto-attempt generation on Splunk start/restart so runtime can resume from local state when gate conditions are already satisfied.
- `workshop_region.py` (`workshopregion action=set`) from Workshop Introduction dashboard flow
  - Purpose: start generation immediately after host selects/saves region in the dashboard (without waiting for a Splunk restart).

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
6. Guard against duplicate workers before spawning:
   - Inspect current process table
   - If `backfill_log.py` is already running, do not spawn another one
   - If `live_log.py` is already running, do not spawn another one
   - If both are already running, exit safely with no new process started
   - If only one is running, spawn only the missing worker

---

## workshop_region.py (dashboard control path)

**Invoked by:** custom search command `workshopregion` from `workshop_introduction` dashboard searches.

**Responsibilities:**
1. `action=status`/`action=get`: read effective config (`default` overlaid by `local`) and return current region/generation/backfill status to dashboard tokens/panels.
2. `action=set`:
   - write `[baseline] region=<au|jp>` to `local/ai_lab_scenarios.conf`
   - write `[baseline] baseline_generation_enabled=true` to `local/ai_lab_scenarios.conf`
   - trigger `launcher.py` (detached subprocess) so generation starts from current local runtime state
3. Emit command result payloads to spool under `var/spool/ai_lab/ai_lab_log/workshop_region/` for ingestion to `index=ai_lab_log`.

**Important nuance:**
- `action=set` can trigger `launcher.py` repeatedly, but `launcher.py` only initializes `backfill_start_time` when missing.
- Repeated `action=set` calls are expected; `launcher.py` now includes a duplicate-process guard so repeated triggers do not start concurrent duplicate `backfill_log.py` / `live_log.py` workers.
- Backfill execution is still gated by `backfill_completed` in `backfill_log.py` (`true` => skip).

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
5. Each NDJSON line must be valid JSON and must only include fields that exist in the corresponding `samples/.../sample.json` template (or `samples/.../README.md` if it explicitly authorizes additional keys).
6. The `{{timestamp}}` placeholder (when present) must be generated as a **timezone-aware, ISO-8601 string with a numeric offset**, using the region’s IANA zone (`Asia/Tokyo` for `jp`, `Australia/Sydney` for `au`) so offsets/DST are correct for each instant. See **Domain timestamps (`{{timestamp}}`) — IANA + ISO-8601** above.
7. **Do not** embed Splunk routing metadata (`index`, `sourcetype`, `source`, `host`) in the JSON unless the sample template/README calls for it. Splunk file monitor stanzas in `default/inputs.conf` are the source of truth for `index=`, `sourcetype=`, and monitor-level `host=` / `source=` (when configured).
8. For telemetry link pairs, enforce directional packet conservation using the bidirectional interface lookup (`lookups/router_if_connected_bidirectional.csv`, fallback `lookups/router_if_connections_bidirectional.csv`): receiver `ifInPktsRate` must not exceed connected peer `ifOutPktsRate` in either direction (loss is allowed; packet creation is not).
9. Telemetry packet drop-rate model requirement: for each linked direction, keep drop rate below 1% in generated baseline data (equivalently, keep inbound rate in the range `0.99 * ifOutPktsRate` to `ifOutPktsRate` when `ifOutPktsRate > 0`).
10. On completion, write `backfill_completed = true` to `local/ai_lab_scenarios.conf`

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
   - Guardrail: do not emit events with a domain timestamp later than current runtime time (no future-dated logs). If scheduler/loop drift occurs, clamp generation cursor to `now`.
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
- Do not introduce abrupt step changes at boundary hours (especially around Fri→Sat and Sun→Mon).
- Apply interpolation windows around Fri→Sat and Sun→Mon transitions so chart behavior stays realistic.
- This transition policy is mandatory across **all generation scripts** (`launcher.py`, `backfill_log.py`, `live_log.py`) and any shared helper logic they use.
- `backfill_log.py` and `live_log.py` must use the same transition model/parameters so historical and real-time curves remain continuous.
- Scope clarification: this smoothing requirement applies to **all generated metrics**, including telemetry `ifInPktsRate` and `ifOutPktsRate`, unless a scenario explicitly defines/activates a sudden step change as part of the test objective.
- Preferred transition windows:
  - ramp-up to weekend: Friday 18:00 -> Saturday 00:00 (region local time)
  - ramp-down to weekday: Sunday 18:00 -> Monday 00:00 (region local time)

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
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:metric`, `host=thousandeyes_at_r9`, `source=ai_lab:backfill:thousandeyes_metric`
- `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_alerts/`  
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:alerts`, `source=ai_lab:backfill:thousandeyes_alerts`
- `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`  
  → `index=telemetry`, `sourcetype=cnc_interface_counter_json`, `host=router_int_count`, `source=ai_lab:backfill:telemetry`

**Monitors and TailReader / CRC:** each spool `monitor://` stanza should set **`crcSalt = <SOURCE>`** (Splunk literal: includes each file’s path in the CRC). Do not use a constant label as `crcSalt` to “fix” header collisions between different files. **`backfill_log.py`** writes each spool file with a **unique basename** (timestamp-derived value and PID) to avoid reusing the same path for unrelated runs. See `docs/project_conf_design.md` and `~/.cursor/skills-cursor/splunk-app-manager/SKILL.md`.

**Derived `alerts` index:** there is no file-ingest `samples/...` path for `alerts` by design. Population strategy is TBD, but it will not be fed by the NDJSON spool pipeline.

**Derived `episode` index:** there is no file-ingest `samples/...` path for `episode` by design. The `episode` index is intended to be materialized from `alerts` (details TBD); do not add sample monitors for `episode` in `inputs.conf`.

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
