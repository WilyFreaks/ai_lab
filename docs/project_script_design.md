# Data Generation Script Design

## Overview

Three scripts under `bin/` handle all synthetic data generation for the workshop app.

```
bin/
├── launcher.py      # entry point, spawned by Splunk scripted input
├── backfill_log.py  # one-shot historical data generation
└── live_log.py      # continuous real-time data generation + scenario trigger
```

**Resume after a break:** Human checklist and paths → `docs/project_ai_lab.md` → *Handoff* → *Resume after a break*. **`live_log.py`** owns **`scenario_happening_probability`** during scenario windows (missing/invalid → **1**). After editing generators or **`default/ai_lab_scenarios.conf`**, restart **`live_log.py`** / **`backfill_log.py`** (or Splunk) if those processes are already running.

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
3. Emit command result payloads to spool under `var/spool/ai_lab/ai_lab_logs/workshop_region/` for ingestion to `index=ai_lab_logs`.

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
3. Generate synthetic events for the window `(backfill_start_time - backfill_days)` → `backfill_start_time` in **one run** (one spool file per configured stream in that invocation). Timestamp step per event: **`<<index>>#<<sourcetype>>#<<sample_file>>#interval`** × 60 seconds **unless** **`<<index>>#<<sourcetype>>#<<sample_file>>#event_interval_sec`** is set — then step in seconds is **`event_interval_sec`** across the whole backfill span.
4. Write generated events in bulk spool files under app spool paths:
   - `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_metric/`
   - `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`
   - `var/spool/ai_lab/telemetry/cnc_srte_path_json/`
   - `var/spool/ai_lab/telemetry/cnc_service_health_json/`
   - `var/spool/ai_lab/twamp/pca_twamp_csv/`
   - `var/spool/ai_lab/syslog/wdm_pm/` (when enabled)
5. Template source files may use `json`, `xml`, `csv`, or `txt` under `samples/.../` (for example `sample.json` or `sample.txt`), and must follow each source template contract documented in `samples/.../README.md` when present.
6. Loader logic must first inspect the template file extension and route to the matching parser/renderer behavior for that format.
7. Output wire format must follow sample extension: `.json` templates emit NDJSON lines; `.csv`/`.xml`/`.txt` templates emit the corresponding text payload format. For `.csv` specifically, follow **CSV templates (`*.csv`)** (single header line at file start; body rendered per event).
8. For sources that emit NDJSON, each line must be valid JSON and should only include fields authorized by the corresponding sample template/README.
9. The `{{timestamp}}` placeholder (when present) must be generated as a **timezone-aware, ISO-8601 string with a numeric offset**, using the region’s IANA zone (`Asia/Tokyo` for `jp`, `Australia/Sydney` for `au`) so offsets/DST are correct for each instant. See **Domain timestamps (`{{timestamp}}`) — IANA + ISO-8601** above.
10. **Do not** embed Splunk routing metadata (`index`, `sourcetype`, `source`, `host`) in payloads unless the sample template/README calls for it. Splunk file monitor stanzas in `default/inputs.conf` are the source of truth for `index=`, `sourcetype=`, and monitor-level `host=` / `source=` (when configured).
11. For telemetry link pairs, enforce directional packet conservation using the bidirectional interface lookup (`lookups/router_if_connected_bidirectional.csv`, fallback `lookups/router_if_connections_bidirectional.csv`): receiver `ifInPktsRate` must not exceed connected peer `ifOutPktsRate` in either direction (loss is allowed; packet creation is not). Optional key `telemetry#cnc_interface_counter_json#sample.json#directional_min_receive_fraction` (default `0.99` when unset) sets the minimum peer inbound as a fraction of outbound; scenario overlays may set it to `0` so only the `ifIn <= ifOut` cap applies and large intentional gaps (e.g. scenario 1) are not clamped upward.
12. Telemetry packet drop-rate model requirement: for each linked direction, keep drop rate below 1% in generated **baseline** data (equivalently, keep inbound rate in the range `directional_min_receive_fraction * ifOutPktsRate` to `ifOutPktsRate` when `ifOutPktsRate > 0` and that fraction is `0.99`). During active scenario windows, scenario config may lower that fraction to allow larger modeled loss on specific links.
13. `scenario_happening_probability` is a common per-source runtime key using this pattern: `<index>#<sourcetype>#<sample_file>#scenario_happening_probability`.
14. During active scenario windows in live generation, evaluate this probability per source/event to decide whether that source uses scenario-overridden values or baseline values (`0` never happens, `1` always happens, clamped to `0..1`).
15. If `scenario_happening_probability` is missing or invalid for a source, treat it as `1` (always happens).
16. **Note:** For **`cnc_service_health_json`**, you normally **omit** `telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability` in **`[scenario_1]`** — missing/invalid values default to **`1`**, so **`SERVICE_DEGRADED`** / score **50** apply on every tick. Set a fractional probability only when you want stochastic baseline fallback (contrast with **`telemetry#cnc_srte_path_json#sample.txt#scenario_happening_probability`**, where fractional values are intentional).
17. When a backfill run actually starts (after gate checks), write `backfill_run_started_time` (epoch seconds, wall clock) to `local/ai_lab_scenarios.conf`. On completion, write `backfill_completed = true` and `backfill_completed_time` (epoch seconds). The `workshopregion` command exposes `backfill_duration` as completed−started seconds when backfill is complete.
18. TWAMP CSV placeholders may be slice-scoped (for example `slice1001_ul_firstpktSeq`, `slice1001_ul_lastpktSeq`, `slice1001_ul_rxpkts`). For each slice/session, packet sequence continuity must be maintained so:
   - no-loss expectation: `ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
   - next-event continuity: `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
19. Runtime sequence continuity must survive restarts by persisting local state under `[baseline]` in `local/ai_lab_scenarios.conf` (for example `sequence_last_value` and TWAMP per-slice/per-session UL packet sequence state).

**Backfill/live boundary continuity:**
`backfill_log.py`'s `end_ts` must be aligned to the same UTC-minute boundary that `live_log.py` uses for its `first_tick`. The formula is:
```python
live_first_tick = ((int(start_anchor) + 59) // 60) * 60
end_ts = live_first_tick  # exclusive upper bound for backfill range()
```
Without this ceiling-minute rounding, the two generators use different time grids and leave exactly one missing tick at the handoff boundary. This fix ensures continuous, gap-free, duplicate-free event generation across the backfill→live transition.

**Restart behavior:** 
If Splunk restarts mid-backfill, `backfill_start_time` is already set in `local/`, so the same time window is used.
In this case, scripts first need to check the latest timestamp of the events before starting synthetic event generation.
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
   - This includes overwrite-capable timing keys such as `<index>#<sourcetype>#<sample_file>#interval`.
4. Generate synthetic events and write to spool files for monitor ingestion only when the current minute matches each source's effective interval schedule (CSV outputs use the same one-header-per-file rule as backfill; see **CSV templates (`*.csv`)**).
   - Example: `interval=5` emits at minute `0,5,10,...,55`.
   - If scenario override sets `interval=30`, emit only at minute `0,30` while override is active.
   - Optional **`<<index>>#<<sourcetype>>#<<sample_file>>#event_interval_sec`** (seconds): when set, each eligible tick emits **multiple** events: `N = max(1, (interval×60) // event_interval_sec)` timestamps ending at the tick, spaced by `event_interval_sec`. When unset, emit **one** event per eligible tick (timestamp = tick). Scenario stanzas may override this key like other `index#sourcetype#sample_file#*` keys.
   - Guardrail: do not emit events with a domain timestamp later than current runtime time (no future-dated logs). If scheduler/loop drift occurs, clamp generation cursor to `now`.
5. Read scenario runtime controls from `[scenarios]` in `local/ai_lab_scenarios.conf`
6. Treat `<scenario>_activated` as activation epoch (`0` means inactive)
7. Apply scenario overrides only during fault window:
   - start: `activated + fault_start * 60`
   - end: `start + fault_duration * 60`
8. Outside fault window, use baseline values
9. Scenario activation state must be evaluated on every scheduler tick (not startup-only) so live behavior reacts immediately to enable/disable actions.
10. For each source, evaluate `<index>#<sourcetype>#<sample_file>#scenario_happening_probability` on each emitted event (using effective baseline/scenario-overridden config) to decide whether to apply scenario-overridden values for that source or fall back to baseline values for that event.
11. For `telemetry#cnc_interface_counter_json#sample.json`, apply scenario reroute controls (if configured) using slice groups:
   - `telemetry#cnc_interface_counter_json#sample.json#reroute_from_slice`
   - `telemetry#cnc_interface_counter_json#sample.json#reroute_to_slice`
   - `telemetry#cnc_interface_counter_json#sample.json#reroute_pct`
   - `telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes`
   - `telemetry#cnc_interface_counter_json#sample.json#reroute_ramp_minutes`
12. `reroute_pct` semantics are conserved: remove traffic from from-slices and redistribute the removed volume to to-slices by baseline-weight share (do not apply independent +pct multipliers on healthy slices).
13. For `scenario_1`, immediate directional gap behavior on `R5->R7` is independent from reroute timing and is configured by:
   - `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_out_key`
   - `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_in_key`
   - `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_pct`
14. For `thousandeyes#cisco:thousandeyes:metric#sample.json`, these metrics may return to baseline after scenario start using per-metric keys:
   - `response_time_ms`
   - `network_latency_ms`
   - `throughput_kbps`
   with:
   - `thousandeyes#cisco:thousandeyes:metric#sample.json#<metric>.back_to_baseline_start_minutes`
   - `thousandeyes#cisco:thousandeyes:metric#sample.json#<metric>.back_to_baseline_ramp_minutes`
15. For `ios#cisco:ios` BFD fault logs (`samples/ios/cisco:ios/sample_bfd.txt`), emit once per `scenario_1` activation:
   - Preferred scenario keys:
     - `ios#cisco:ios#sample_bfd.txt#interval = once`
     - `ios#cisco:ios#sample_bfd.txt#start_minutes = <delay_after_activation>`
   - Effective one-shot emit epoch:
     - `scenario_1_activated + scenario_1_fault_start*60 + ios#cisco:ios#sample_bfd.txt#start_minutes*60`
   - Backward compatibility fallback when `start_minutes` is missing:
     - `scenario_1_activated + scenario_1_fault_start*60 + telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes*60`
   - The emitted `{{timestamp}}` in IOS BFD lines must align to this reroute-start epoch (not initial activation epoch).
   - Persist per-activation emit state in local runtime keys so restart does not duplicate BFD sequence for the same activation.
16. For scenario one-shot streams (for example IOS BFD and `syslog#wdm_alert#sample.xml`), emit-state tracking must be keyed by `scenario + stream` (not scenario-only), so multiple one-shot sources can each emit once for the same activation without suppressing each other.

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
- **Delay/jitter integer wobble:** After the base value (including `daily_min`/`daily_max` and hourly `peak_rate_*`), delay/jitter fields add `noise_stdev * ε` where **ε is one `N(0,1)` draw per slice per event** (shared across all noisy metrics for that slice). Wire output stays **integer** (`int(round(...))`); a typical `twamp#pca_twamp_csv#sample.csv#default.noise_stdev` around **0.45** makes minute-to-minute charts visibly lively while preserving plausible percentile ordering within a row.
- **Splunk emit schedule (minutes):** `twamp#pca_twamp_csv#sample.csv#interval` in `[baseline]` is the generator **emit period in minutes** — it gates how often `live_log.py` considers writing new `pca_twamp_csv` events on the 1-minute orchestrator (`minute % interval == 0`). `backfill_log.py` uses the same keys for timestamp stride **unless** `event_interval_sec` applies (see below).
- **Optional `event_interval_sec`:** `<<index>>#<<sourcetype>>#<<sample_file>>#event_interval_sec` in seconds. When set, `live_log.py` emits **multiple** rows per eligible tick; `backfill_log.py` steps synthetic timestamps by `event_interval_sec` through the backfill window. When unset, behavior is one event per **`interval`** minutes (live) and **`interval`×60** seconds between backfill events. Detail: `samples/twamp/pca_twamp_csv/README.md` (*Splunk generation cadence vs PCA row window*).
- **In-record window (PCA CSV fields):** The TWAMP `sample.csv` carries an **`Interval`** column (seconds; shipped template uses `10`). The **`intervalms`** column is filled via placeholder `{{intervalms}}`, resolved from config key **`twamp#pca_twamp_csv#sample.csv#intervalms`** (milliseconds, e.g. `10000` for 10 s). Keep **`intervalms`** aligned with **`Interval`** (`intervalms = Interval * 1000`) when both describe the same window. Relate **`Packet Rate` (pps)** to **`*_rxpkts_expected`** with the same **`window_seconds`** (typically `Interval` or `intervalms/1000`): expected count ≈ **`Packet Rate * window_seconds`** before drop-rate adjustment. Documented in detail under `samples/twamp/pca_twamp_csv/README.md` (*Splunk generation cadence vs PCA row window*).
- Use a shared per-tick/per-slice loss context during scenario windows so TWAMP loss and telemetry directional packet-rate gaps move together.
- Sequence continuity (per TWAMP slice/session) must hold across backfill, live generation, and restarts:
  - `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
  - `expected_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
  - no-loss case: `ul_rxpkts = expected_rxpkts`
  - loss case: `ul_rxpkts = max(0, expected_rxpkts - ul_lostpkts)`
- After `apply_twamp_ul_packet_sequence` computes `*_rxpkts` from `*_rxpkts_expected` and `*_rxpkts_drop_rate`, it sets `*_lostpkts = max(0, expected - rx)` and `*_lostperc = round(100 * lost / expected)` (**integer percent 0–100**, **`0` if expected is `0`**), overwriting CSV placeholders so exported loss columns match sequence math and scenario dashboard 0–100% loss charts.
- Persist TWAMP sequence state in `local/ai_lab_scenarios.conf` runtime keys so restart does not reset packet sequence continuity.

### Baseline verification (scripts + saved searches)

- `scripts/test_baseline.sh` runs `scripts/test_backfill.sh`, which invokes saved searches `twamp_event_count` (minute buckets in the last 5m), `twamp_dmean`, and `twamp_jmean` against `index=twamp` / `pca_twamp_csv`, comparing rolling averages to `default/ai_lab_scenarios.conf` `daily_min` / `daily_max` (with noise tolerance), and **`assert_thousandeyes_trend_per_day`** (ratio of medians at two Wednesday checkpoints vs `trend_per_day` from `backfill_head_time`). See `docs/project_test_design.md` and `default/savedsearches.conf`.

### TWAMP peak-rate fallback strategy

To avoid massive per-placeholder config growth for `pca_twamp_csv`, support a global fallback peak curve:

- `twamp#pca_twamp_csv#sample.csv#default.peak_rate_00` ... `twamp#pca_twamp_csv#sample.csv#default.peak_rate_23`

Recommended precedence for TWAMP peak-rate lookup:

1. `twamp#pca_twamp_csv#sample.csv#<placeholder>.peak_rate_<HH>` (most specific)
2. `twamp#pca_twamp_csv#sample.csv#<group>.peak_rate_<HH>` (optional group level; for example `ul`, `dl`, `rt`)
3. `twamp#pca_twamp_csv#sample.csv#default.peak_rate_<HH>` (global fallback)

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
- To avoid hard step changes at hour boundaries, generators interpolate per minute between the current hour's `peak_rate_<HH>` and the next hour's `peak_rate_<HH+1>`.
- **`peak_rate_<HH>` is the rate at the middle of hour HH (i.e. HH:30), not the top of the hour (HH:00).** Implementation: shift the local time by −30 minutes before computing the hour and minute-progress interpolation in `interpolated_hourly_peak_rate()`. Effect: at HH:30 the rate equals `peak_rate_<HH>` exactly; at HH:00 the rate is halfway between `peak_rate_<HH-1>` and `peak_rate_<HH>`; transitions occur smoothly across the ±30-minute window.
- Region timezone mapping must be deterministic and shared by backfill/live logic.

Design intent:

- Workshop host selects region once in `workshop_introduction`.
- Synthetic daily seasonality then follows that region’s local business/overnight rhythm consistently in both historical and live generation.

---

## Day-to-Day Variation (`daily_variation_stdev`)

Without extra configuration, the same hour on the same day of week looks identical across weeks because the diurnal curve (`peak_rate_*`) and `daily_min`/`daily_max` are fixed. `noise_stdev` only adds tick-level jitter, which averages out over an hour.

To produce realistic week-over-week variation, each metric prefix supports an optional key:

```
<prefix>.daily_variation_stdev = 0.08
```

**Behaviour:**
- A multiplicative factor is drawn from `N(1.0, daily_variation_stdev)` once per calendar date per metric.
- The seed is `MD5(local_date | section | prefix)` — deterministic: the same date always produces the same factor for the same metric in both backfill and live generation.
- Different metrics on the same day get independent factors by default **except** for telemetry interface packet rates on **paired ends of the same physical link** (see below).
- Result is clamped to `[0.2, 2.0]` to prevent pathological extremes.

**Paired-link exception (`cnc_interface_counter_json` rates):**

- For placeholders ending in **`ifOutPktsRate`** / **`ifInPktsRate`** that belong to opposite router interfaces on one physical link (`lookups/router_if_connections*.csv`), generators derive a **canonical shared seed prefix** so **both directions get the same daily factor** (`build_link_dvar_seed_map` in `bin/backfill_log.py` / `bin/live_log.py`).
- **Why:** Scenario **`directional_min_receive_fraction = 0`** disables inbound “pull up toward outbound” clamping; uncorrelated random daily factors would paint **fake asymmetric gaps** on healthy links that are visualization noise, not story intent.
- **Implementation rule:** `bin/backfill_log.py` and **`bin/live_log.py` must stay in lockstep** for this path (shared helpers such as `interface_to_placeholder_token`, map construction, and `daily_variation_multiplier(..., seed_prefix=...)`). Changing one file without the other has broken live generation in the past.
- Applied in `metric_value()` after `weekend_multiplier` and before the outlier/noise step.
- Omitting the key (or setting it to `0`) disables the feature — no change in existing behaviour.

**Tuning guidance:**

| Value | Visible effect |
|---|---|
| `0.0` | Disabled — identical curve every day |
| `0.05` | Subtle ±5% day-to-day drift |
| `0.08` | Moderate ±8% variation (shipped default) |
| `0.15` | Pronounced variation; weekly pattern still recognisable |

The shipped `default/ai_lab_scenarios.conf` sets `daily_variation_stdev = 0.08` for every metric that already has a `noise_stdev` entry (ThousandEyes, telemetry interface counters, TWAMP defaults).

---

## Long-Term Trend (`trend_per_day`)

Day-to-day variation (`daily_variation_stdev`) adds random scatter but no directional drift. `trend_per_day` adds a linear upward or downward slope across the **synthetic baseline history**, measured **from `backfill_head_time`** — not from `backfill_start_time` (workshop-lock / backfill tail).

**Rule:** **`days_elapsed = 0` at `backfill_head_time`.** Workshop status and dashboards expose this value as **`backfill_head_time`** (`workshopregion` computes it when the key is not in conf).

```
<prefix>.trend_per_day = 0.05   # +5% per day (negative = decline)
```

**Behaviour:**
- Multiplier at tick `t`: `1.0 + trend_per_day × days_elapsed`
- **`days_elapsed`** = `(local_dt.timestamp() − trend_zero) / 86400`, clamped to ≥ 0.
- **`trend_zero`** (same logical instant as **`backfill_head_time`**) =
  - `[baseline].backfill_head_time` (epoch seconds) when explicitly set in **`local/ai_lab_scenarios.conf`** or **`default/ai_lab_scenarios.conf`**, otherwise
  - **`backfill_start_time − backfill_days×86400`** (computed synthetic window head — matches dashboard / `workshopregion` metadata when the key is unset).
  - Omitting **`backfill_start_time`** ⇒ **`trend_multiplier` returns `1.0`** (no trend).
- Persist **`backfill_head_time`** in **`[baseline]`** if **`backfill_days`** changes after a lock and generated **and** dashboards must keep a fixed drift origin; otherwise the generators derive head from **`backfill_start_time`** and current **`backfill_days`**.
- Result clamped to `[0.05, 10.0]` to prevent runaway extremes.
- Applied in `metric_value()` after `daily_variation_multiplier` and before outlier/noise.
- Omitting the key (or `0.0`) disables the feature — no change to existing behaviour.

**Shipped defaults (`default/ai_lab_scenarios.conf`):**
- All telemetry `ifOutPktsRate` and `ifInPktsRate` metrics: `trend_per_day = 0.03`
- ThousandEyes `response_time_ms`, `throughput_kbps`, `network_latency_ms`, `network_jitter_ms`: `trend_per_day = 0.03`
- TWAMP: **no trend** — delay/jitter stays flat as long as the link has headroom; it only spikes when utilisation hits capacity (modelled by scenario_1)

**Effect at 3%/day over a 14-day backfill window:**

| Day | Multiplier | Δ from baseline |
|---|---|---|
| 0 | 1.00 | 0% |
| 1 | 1.03 | +3% |
| 3 | 1.09 | +9% |
| 7 | 1.21 | +21% |
| 14 | 1.42 | +42% |

This gives a clearly visible upward slope in baseline interface counters (and ThousandEyes metrics that set `trend_per_day`) over the synthetic history. A 42% total increase between backfill head and tail tells a credible "capacity is being consumed" story while leaving room for the scenario_1 spike on top (TWAMP itself remains untrended in shipped defaults).


## Ingestion Routing (inputs.conf monitors)

Scripted input launches `launcher.py` only. Event ingestion is file-based via monitor stanzas:

- `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_metric/`  
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:metric`, `host=thousandeyes_at_r9`, `source=ai_lab:backfill:thousandeyes_metric`
- `var/spool/ai_lab/thousandeyes/cisco_thousandeyes_alert/`
  → `index=thousandeyes`, `sourcetype=cisco:thousandeyes:alert`, `source=ai_lab:backfill:thousandeyes_alert`
- `var/spool/ai_lab/telemetry/cnc_interface_counter_json/`  
  → `index=telemetry`, `sourcetype=cnc_interface_counter_json`, `host=router_int_count`, `source=ai_lab:backfill:telemetry`
- `var/spool/ai_lab/telemetry/cnc_srte_path_json/`  
  → `index=telemetry`, `sourcetype=cnc_srte_path_json`, base monitor host is `cnc_srte_path`, and per-event host metadata is overridden from payload `vlan` via `props.conf` + `transforms.conf` index-time transform
- `var/spool/ai_lab/telemetry/cnc_service_health_json/`  
  → `index=telemetry`, `sourcetype=cnc_service_health_json`, `host=cnc_service_health`, `source=ai_lab:script:telemetry`
- `var/spool/ai_lab/twamp/pca_twamp_csv/`  
  → `index=twamp`, `sourcetype=pca_twamp_csv`, `host=twamp_pca`, `source=ai_lab:script:twamp` each spool `monitor://` stanza should set **`crcSalt = <SOURCE>`** (Splunk literal: includes each file’s path in the CRC). Do not use a constant label as `crcSalt` to “fix” header collisions between different files. **`backfill_log.py`** writes each spool file with a **unique basename** (timestamp-derived value and PID) to avoid reusing the same path for unrelated runs. See `docs/project_conf_design.md` and `~/.cursor/skills-cursor/splunk-app-manager/SKILL.md`.
- `var/spool/ai_lab/ios/cisco_ios/`  
  → `index=ios`, `sourcetype=cisco:ios`, `host=ios_router`, `source=ai_lab:script:ios`
- `var/spool/ai_lab/syslog/wdm_alert/` (when enabled)  
  → `index=syslog`, `sourcetype=wdm_alert`, base monitor host may be static, and per-event host metadata should be overridden from XML alias `NativeEMSName` via `props.conf` + `transforms.conf` (`set_host_from_wdm_alert_xml`)
- `var/spool/ai_lab/syslog/wdm_pm/` (when enabled)  
  → `index=syslog`, `sourcetype=wdm_pm`; payload should include endpoint identity fields compatible with `lookups/router_wdm_transponders.csv` so searches can join route A/Z interfaces and bound transponder ports.

**Derived `alerts` index:** there is no file-ingest `samples/...` path for `alerts` by design. Population is scheduled-search output (for example `Interface Counter Mismatch`, `Packet Loss Threshold Exceeded`, and `CNC Service Health Status Degraded` stanzas in `default/savedsearches.conf`) and should emit `sourcetype=ai_lab_alert`.

**Derived `episode` index:** there is no file-ingest `samples/...` path for `episode` by design. The `episode` index is intended to be materialized from `alerts`; until dedicated materialization is enabled, scenario dashboards may compute episode summaries directly from `index=alerts`. Do not add sample monitors for `episode` in `inputs.conf`.

## WDM PM generation contract

When `wdm_pm` generation is implemented, treat it as a structured CSV stream under `samples/syslog/wdm_pm/`.

- Source mapping:
  - Use `lookups/router_wdm_transponders.csv` as the route-to-transponder binding source.
  - Emit endpoint records with deterministic A/Z orientation (no random side swaps between ticks).
- Required metrics:
  - `LSBIASCUR`, `SUMOOPCUR` (Tx-domain)
  - `FEC_BEF_COR_ER`, `SUMIOPCUR` (Rx-domain)
  - `BDTEMPCUR`, `EDTMPCUR` (device context)
- Scope:
  - Prefer one logical record per endpoint per tick (or equivalent row granularity clearly documented in sample README).
  - Keep metric names unchanged and present in every emitted endpoint record.

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
- Command script `bin/scenario_control.py` reads effective config (default overlaid by `local/`) for `action=status` / `action=get`, and writes scenario runtime values to `local/ai_lab_scenarios.conf` for `action=set` (omit `action` to keep backward compatibility with the set path when `active` is passed).
- Activation behavior:
  - Enable: if `<scenario>_activated` is already non-zero, preserve it; otherwise set to current epoch time
  - Disable: set `<scenario>_activated` to `0`
- **Activation safeguard (`active=1`):** `scenario_control.py` must reject activation (`active=1`) with an error message if either of the following conditions are not met in `local/ai_lab_scenarios.conf`:
  - `[baseline].region` is a valid value (`au` or `jp`) — region must be locked
  - `[baseline].backfill_completed = true` — backfill must have completed
  - This prevents scenarios from being activated before the workshop data foundation is ready. The command returns `status=error` and a descriptive `message` so the dashboard can display the rejection reason.

## spool_cleanup.py

**Invoked by:** Splunk scripted input (`interval = 3600` in `default/inputs.conf`)

**Runs:** Once on Splunk startup, then every 3600 seconds (1 hour).

**Responsibilities:**
1. Locate `var/spool/ai_lab/` relative to the app directory.
2. Walk the entire spool tree and delete any **file** whose `mtime` is older than 4 hours (`AGE_THRESHOLD_HOURS = 4`).
3. Preserve directory structure — only files are removed.
4. Emit a single JSON line to stdout summarising the run (fields: `timestamp`, `status`, `spool_root`, `age_threshold_hours`, `deleted_count`, `error_count`, `deleted_files`, `errors`).

**Splunk ingestion:** stdout is captured as `index=ai_lab_logs sourcetype=ai_lab:spool_cleanup`.

**Activation:** A Splunk restart or app reload registers the scripted input automatically.

**Threshold guidance:** Do not lower the 4-hour threshold below the longest expected Splunk monitor polling cycle; doing so risks deleting spool files before `splunkd` has ingested them.

**Verification search:**
```
index=ai_lab_logs sourcetype=ai_lab:spool_cleanup | table _time deleted_count error_count
```

---

## `reset_workshop_state.sh` packaging sync

Before destructive reset actions, `scripts/reset_workshop_state.sh` now performs a packaging sync from `local/` to `default/` so workshop UI/search edits are preserved in Git-tracked defaults:

- `local/savedsearches.conf` -> `default/savedsearches.conf` (full-file replacement when local file exists)
- `local/data/ui/views/*.xml` -> `default/data/ui/views/<same-name>.xml` (per-file full replacement for each local dashboard XML)
- `metadata/local.meta` merged into `metadata/default.meta` via `scripts/merge_local_meta_to_default_meta.py` when `local.meta` exists: Splunk UI metadata stanzas are merged into `default.meta`, **`[savedsearches/...]`** rows are dropped unless a matching stanza exists in **`default/savedsearches.conf`** (evaluated after the savedsearches copy above), and **`owner = admin`** in merged bodies is rewritten to **`owner = nobody`**. If **`metadata/local.meta`** is absent, this step is skipped.

Then the script continues with the existing reset order:

1. Stop app generator workers (`backfill_log.py` / `live_log.py`) and confirm no orphan `launcher.py`/`backfill_log.py`/`live_log.py`
2. Stop Splunk
3. Clean app spool under `var/spool/ai_lab`
4. Remove app index data under `$SPLUNK_DB`
5. Remove `local/ai_lab_scenarios.conf`
6. Start Splunk and verify app indexes are empty
