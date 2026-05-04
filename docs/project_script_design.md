# Data Generation Script Design

## Overview

Three scripts under `bin/` handle all synthetic data generation for the workshop app.

```
bin/
├── launcher.py      # entry point, spawned by Splunk scripted input
├── backfill_log.py  # one-shot historical data generation
└── live_log.py      # continuous real-time data generation + scenario trigger
```

## Sample Template Formats

Sample files under `samples/` are source-specific templates and are **not limited to JSON files**.

- Allowed template formats include `json`, `xml`, `csv`, and `txt`.
- Choose template format per sourcetype/data shape requirement, not by a global single-format rule.
- `txt` is the most flexible option for unstructured or mixed-format payload templates.
- Scripts must check the sample file extension first (for example `.json`, `.xml`, `.csv`, `.txt`) and then apply the corresponding load/render logic path.
- Generator parsing/rendering may use source-specific handlers so each source can load/render its template safely.
- Current implemented streams use `.json` and `.txt` templates, and generated spool payload format follows the sample extension (`.json` -> NDJSON, `.csv` -> CSV text, `.xml` -> XML text, `.txt` -> plain text).

### CSV templates (`*.csv`)

For CSV samples (for example `twamp` / `pca_twamp_csv`), `backfill_log.py` and `live_log.py` treat the template as **one header row plus a body**:

- **First line** of the sample file is the **column header**. It is written **only once** at the beginning of each spool output file so Splunk’s CSV extraction (`INDEXED_EXTRACTIONS = csv`, `TIMESTAMP_FIELDS`, etc.) sees a single header for the file.
- **All lines after the first** are the **body template** (may be multiple rows per event). That body is rendered **for every event** (each time step); new output is appended **without** repeating the header line.

Placeholders `{{...}}` must appear only in the body; the header line should be fixed column names only. The TWAMP contract is documented in `samples/twamp/pca_twamp_csv/README.md`.

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
3. Generate synthetic events for the window `(backfill_start_time - backfill_days)` → `backfill_start_time` in **one run** (one spool file per configured stream in that invocation). Timestamp step per event: **`<<index>>#<<sourcetype>>#interval`** × 60 seconds **unless** **`<<index>>#<<sourcetype>>#event_interval_sec`** is set — then step in seconds is **`event_interval_sec`** across the whole backfill span.
4. Write generated events in bulk spool files under app spool paths:
   - `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_metric/`
   - `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`
   - `var/spool/ai_lab/telemetry/cnc_srte_path_json/`
   - `var/spool/ai_lab/telemetry/cnc_service_health_json/`
   - `var/spool/ai_lab/twamp/pca_twamp_csv/`
5. Template source files may use `json`, `xml`, `csv`, or `txt` under `samples/.../` (for example `sample.json` or `sample.txt`), and must follow each source template contract documented in `samples/.../README.md` when present.
6. Loader logic must first inspect the template file extension and route to the matching parser/renderer behavior for that format.
7. Output wire format must follow sample extension: `.json` templates emit NDJSON lines; `.csv`/`.xml`/`.txt` templates emit the corresponding text payload format. For `.csv` specifically, follow **CSV templates (`*.csv`)** (single header line at file start; body rendered per event).
8. For sources that emit NDJSON, each line must be valid JSON and should only include fields authorized by the corresponding sample template/README.
9. The `{{timestamp}}` placeholder (when present) must be generated as a **timezone-aware, ISO-8601 string with a numeric offset**, using the region’s IANA zone (`Asia/Tokyo` for `jp`, `Australia/Sydney` for `au`) so offsets/DST are correct for each instant. See **Domain timestamps (`{{timestamp}}`) — IANA + ISO-8601** above.
10. **Do not** embed Splunk routing metadata (`index`, `sourcetype`, `source`, `host`) in payloads unless the sample template/README calls for it. Splunk file monitor stanzas in `default/inputs.conf` are the source of truth for `index=`, `sourcetype=`, and monitor-level `host=` / `source=` (when configured).
11. For telemetry link pairs, enforce directional packet conservation using the bidirectional interface lookup (`lookups/router_if_connected_bidirectional.csv`, fallback `lookups/router_if_connections_bidirectional.csv`): receiver `ifInPktsRate` must not exceed connected peer `ifOutPktsRate` in either direction (loss is allowed; packet creation is not).
12. Telemetry packet drop-rate model requirement: for each linked direction, keep drop rate below 1% in generated baseline data (equivalently, keep inbound rate in the range `0.99 * ifOutPktsRate` to `ifOutPktsRate` when `ifOutPktsRate > 0`).
13. `scenario_happening_probability` is a common per-source runtime key using this pattern: `<index>#<sourcetype>#scenario_happening_probability`.
14. During active scenario windows in live generation, evaluate this probability per source/event to decide whether that source uses scenario-overridden values or baseline values (`0` never happens, `1` always happens, clamped to `0..1`).
15. If `scenario_happening_probability` is missing or invalid for a source, treat it as `1` (always happens).
16. When a backfill run actually starts (after gate checks), write `backfill_run_started_time` (epoch seconds, wall clock) to `local/ai_lab_scenarios.conf`. On completion, write `backfill_completed = true` and `backfill_completed_time` (epoch seconds). The `workshopregion` command exposes `backfill_duration` as completed−started seconds when backfill is complete.
17. TWAMP CSV placeholders may be slice-scoped (for example `slice1001_ul_firstpktSeq`, `slice1001_ul_lastpktSeq`, `slice1001_ul_rxpkts`). For each slice/session, packet sequence continuity must be maintained so:
   - no-loss expectation: `ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
   - next-event continuity: `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
18. Runtime sequence continuity must survive restarts by persisting local state under `[baseline]` in `local/ai_lab_scenarios.conf` (for example `sequence_last_value` and TWAMP per-slice/per-session UL packet sequence state).

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
2. Run a fixed scheduler tick every minute (single orchestrator loop).
3. On every minute tick, re-read baseline/scenario runtime controls and recompute effective parameters before deciding whether to emit each data source.
   - Baseline values are the default.
   - Active scenario values overwrite corresponding baseline keys during the scenario fault window.
   - This includes overwrite-capable timing keys such as `<source>#interval`.
4. Generate synthetic events and write to spool files for monitor ingestion only when the current minute matches each source's effective interval schedule (CSV outputs use the same one-header-per-file rule as backfill; see **CSV templates (`*.csv`)**).
   - Example: `interval=5` emits at minute `0,5,10,...,55`.
   - If scenario override sets `interval=30`, emit only at minute `0,30` while override is active.
   - Optional **`<<index>>#<<sourcetype>>#event_interval_sec`** (seconds): when set, each eligible tick emits **multiple** events: `N = max(1, (interval×60) // event_interval_sec)` timestamps ending at the tick, spaced by `event_interval_sec`. When unset, emit **one** event per eligible tick (timestamp = tick). Scenario stanzas may override this key like other `index#sourcetype#*` keys.
   - Guardrail: do not emit events with a domain timestamp later than current runtime time (no future-dated logs). If scheduler/loop drift occurs, clamp generation cursor to `now`.
5. Read scenario runtime controls from `[scenarios]` in `local/ai_lab_scenarios.conf`
6. Treat `<scenario>_activated` as activation epoch (`0` means inactive)
7. Apply scenario overrides only during fault window:
   - start: `activated + fault_start * 60`
   - end: `start + fault_duration * 60`
8. Outside fault window, use baseline values
9. Scenario activation state must be evaluated on every scheduler tick (not startup-only) so live behavior reacts immediately to enable/disable actions.
10. For each source, evaluate `<index>#<sourcetype>#scenario_happening_probability` on each emitted event (using effective baseline/scenario-overridden config) to decide whether to apply scenario-overridden values for that source or fall back to baseline values for that event.

**Restart behavior:** 
If Splunk restarts and `backfill_start_time` is already set in `local/`, that indicates live_log.py needs to backfill the live events.
Check the latest timestamp of the events and backfill the events up to the current timestamp.
This is mandatory to avoid missing data.

Implementation note (phase 1 baseline mode):

- `live_log.py` persists minute cursor state in `local/ai_lab_scenarios.conf`:
  - `[baseline] live_last_tick_epoch = <epoch_seconds>`
- `live_log.py` also resumes sequence continuity from persisted local state (including TWAMP UL packet sequence state) so counters continue after backfill handoff and after restarts.
- First run: starts from minute-aligned `backfill_start_time`.
- Subsequent runs/restarts: resume from `live_last_tick_epoch + 60` and catch up minute ticks up to now.

---

## Production Data Quality Requirements

- Weekend/weekday transitions must be smooth in production generation logic.
- Do not introduce abrupt step changes at boundary hours (especially around Fri→Sat and Sun→Mon).
- Apply interpolation windows around Fri→Sat and Sun→Mon transitions so chart behavior stays realistic.
- This transition policy is mandatory across **all generation scripts** (`launcher.py`, `backfill_log.py`, `live_log.py`) and any shared helper logic they use.
- `backfill_log.py` and `live_log.py` must use the same transition model/parameters so historical and real-time curves remain continuous.
- Scope clarification: this smoothing requirement applies to **all generated metrics**, including telemetry `ifInPktsRate` and `ifOutPktsRate`, unless a scenario explicitly defines/activates a sudden step change as part of the test objective.
- Telemetry packet-rate smoothing should cap per-tick deltas for `ifOutPktsRate`/`ifInPktsRate` to keep transitions gradual under baseline tests (consistent with threshold logic derived from config range/noise).
- Preferred transition windows:
  - ramp-up to weekend: Friday 18:00 -> Saturday 00:00 (region local time)
  - ramp-down to weekday: Sunday 18:00 -> Monday 00:00 (region local time)

## TWAMP + Telemetry Correlation Contract

This contract applies when generating `index=twamp sourcetype=pca_twamp_csv` together with `index=telemetry sourcetype=cnc_interface_counter_json`.

- Packet-rate interpretation: treat packet-rate style fields as packets per second (pps). Sampling cadence (for example 1 minute or 10 seconds) is a reporting interval, not the unit definition.
- **Splunk emit schedule (minutes):** `twamp#pca_twamp_csv#interval` in `[baseline]` is the generator **emit period in minutes** — it gates how often `live_log.py` considers writing new `pca_twamp_csv` events on the 1-minute orchestrator (`minute % interval == 0`). `backfill_log.py` uses the same keys for timestamp stride **unless** `event_interval_sec` applies (see below).
- **Optional `event_interval_sec`:** `<<index>>#<<sourcetype>>#event_interval_sec` in seconds. When set, `live_log.py` emits **multiple** rows per eligible tick; `backfill_log.py` steps synthetic timestamps by `event_interval_sec` through the backfill window. When unset, behavior is one event per **`interval`** minutes (live) and **`interval`×60** seconds between backfill events. Detail: `samples/twamp/pca_twamp_csv/README.md` (*Splunk generation cadence vs PCA row window*).
- **In-record window (PCA CSV fields):** The TWAMP `sample.csv` carries an **`Interval`** column (seconds; shipped template uses `10`). The **`intervalms`** column is filled via placeholder `{{intervalms}}`, resolved from config key **`twamp#pca_twamp_csv#intervalms`** (milliseconds, e.g. `10000` for 10 s). Keep **`intervalms`** aligned with **`Interval`** (`intervalms = Interval * 1000`) when both describe the same window. Relate **`Packet Rate` (pps)** to **`*_rxpkts_expected`** with the same **`window_seconds`** (typically `Interval` or `intervalms/1000`): expected count ≈ **`Packet Rate * window_seconds`** before drop-rate adjustment. Documented in detail under `samples/twamp/pca_twamp_csv/README.md` (*Splunk generation cadence vs PCA row window*).
- Use a shared per-tick/per-slice loss context during scenario windows so TWAMP loss and telemetry directional packet-rate gaps move together.
- Sequence continuity (per TWAMP slice/session) must hold across backfill, live generation, and restarts:
  - `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
  - `expected_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
  - no-loss case: `ul_rxpkts = expected_rxpkts`
  - loss case: `ul_rxpkts = max(0, expected_rxpkts - ul_lostpkts)`
- Persist TWAMP sequence state in `local/ai_lab_scenarios.conf` runtime keys so restart does not reset packet sequence continuity.

### Baseline verification (scripts + saved searches)

- `scripts/test_baseline.sh` runs `scripts/test_backfill.sh`, which invokes saved searches `twamp_event_count_test` (minute buckets in the last 5m), `twamp_dmean_test`, and `twamp_jmean_test` against `index=twamp` / `pca_twamp_csv`, comparing rolling averages to `default/ai_lab_scenarios.conf` `daily_min` / `daily_max` (with noise tolerance). See `docs/project_test_design.md` and `default/savedsearches.conf`.

### TWAMP peak-rate fallback strategy

To avoid massive per-placeholder config growth for `pca_twamp_csv`, support a global fallback peak curve:

- `twamp#pca_twamp_csv#default.peak_rate_00` ... `twamp#pca_twamp_csv#default.peak_rate_23`

Recommended precedence for TWAMP peak-rate lookup:

1. `twamp#pca_twamp_csv#<placeholder>.peak_rate_<HH>` (most specific)
2. `twamp#pca_twamp_csv#<group>.peak_rate_<HH>` (optional group level; for example `ul`, `dl`, `rt`)
3. `twamp#pca_twamp_csv#default.peak_rate_<HH>` (global fallback)

Design intent:

- Keep baseline config compact by default.
- Allow targeted per-field overrides only where needed.
- Prefer using peak-rate curves on a small set of TWAMP driver metrics, then derive dependent metrics in code, rather than defining hourly peaks for every TWAMP placeholder.

## Region Timezone Alignment (peak_rate_*)

`peak_rate_00` ... `peak_rate_23` must be evaluated using the local hour of the region selected in `workshop_introduction` (stored in `local/ai_lab_scenarios.conf` `[baseline] region`), not server-local time.

Scope:

- Applies to both `backfill_log.py` and `live_log.py`.
- Applies to all metrics that use hourly `peak_rate_*` curves.

Behavior:

- Same UTC timestamp may map to different `peak_rate_*` keys depending on selected region.
- Hour lookup for `peak_rate_<HH>` must use region-local wall-clock hour (`HH` in `00..23`).
- To avoid hard step changes at hour boundaries, generators should interpolate per minute between the current hour's `peak_rate_<HH>` and the next hour's `peak_rate_<HH+1>`.
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
- `var/spool/ai_lab/telemetry/cnc_srte_path_json/`  
  → `index=telemetry`, `sourcetype=cnc_srte_path_json`, base monitor host is `cnc_srte_path`, and per-event host metadata is overridden from payload `vlan` via `props.conf` + `transforms.conf` index-time transform
- `var/spool/ai_lab/telemetry/cnc_service_health_json/`  
  → `index=telemetry`, `sourcetype=cnc_service_health_json`, `host=cnc_service_health`, `source=ai_lab:script:telemetry`
- `var/spool/ai_lab/twamp/pca_twamp_csv/`  
  → `index=twamp`, `sourcetype=pca_twamp_csv`, `host=twamp_pca`, `source=ai_lab:script:twamp` each spool `monitor://` stanza should set **`crcSalt = <SOURCE>`** (Splunk literal: includes each file’s path in the CRC). Do not use a constant label as `crcSalt` to “fix” header collisions between different files. **`backfill_log.py`** writes each spool file with a **unique basename** (timestamp-derived value and PID) to avoid reusing the same path for unrelated runs. See `docs/project_conf_design.md` and `~/.cursor/skills-cursor/splunk-app-manager/SKILL.md`.

**Derived `alerts` index:** there is no file-ingest `samples/...` path for `alerts` by design. Population strategy is TBD, but it will not be fed by the NDJSON spool pipeline.

**Derived `episode` index:** there is no file-ingest `samples/...` path for `episode` by design. The `episode` index is intended to be materialized from `alerts` (details TBD); do not add sample monitors for `episode` in `inputs.conf`.

---

## State in local/ai_lab_scenarios.conf

Runtime keys written by generators / commands (non-exhaustive):

- `backfill_run_started_time` — wall-clock epoch when `backfill_log.py` began the current run (not the synthetic data anchor).
- `backfill_completed_time` — wall-clock epoch when backfill finished successfully.
- `backfill_completed` — `true` after a successful full run.

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
