---
name: ai_lab_scenarios.conf Design Decisions
description: Conventions and design decisions for the scenario conf file and sample data generation
type: project
originSessionId: 023ba004-a2ab-41d3-9152-4eb0746bfa20
---
# ai_lab_scenarios.conf Design

## Key Conventions

**Conf key naming:** `index#sourcetype#placeholder_name`
- Example: `thousandeyes#cisco:thousandeyes:metric#response_time_ms = 150`
- Same name used in sample template placeholders: `{{response_time_ms}}`
- This avoids any mapping table — direct substitution.

**Placeholder syntax in sample templates:** `{{placeholder_name}}`

## Baseline Stanza

`[baseline]` defines the backfill process — the normal period before the scenario runs.

Key parameter: `backfill_days` (not `duration`) — how many days of historical logs to generate when the app starts.

## Value Variation Model

For each metric parameter, optional suffixes control the variation:

```ini
param = base_value                         # flat value (used if no daily variation needed)
param.daily_min = X                        # min value across the day
param.daily_max = Y                        # max value across the day
param.peak_rate_00 = 0.1                   # rate for hour 00 (0.0=min, 1.0=max)
...
param.peak_rate_23 = 0.1
param.weekend_multiplier = 0.6            # applied on weekends
param.noise_stdev = Z                      # Gaussian noise (absolute units, not %)
param.outlier_probability = 0.0001        # fraction of events that are outliers
param.outlier_min = A
param.outlier_max = B
param.interval = 1                         # how often (minutes) to generate events
```

**Formula:** `value = daily_min + (daily_max - daily_min) × peak_rate`
then add `random.gauss(0, noise_stdev)`

**Hour-boundary smoothing:** `peak_rate` should be interpolated per minute between `peak_rate_<HH>` and `peak_rate_<HH+1>` (region-local wall-clock) to avoid direct step jumps on the hour.

**Weekend transition:** smoothly interpolates multiplier over 2 hours around Fri→Sat and Sun→Mon boundaries (not an abrupt switch).

**Note:** `noise_stdev` (not `noise_stddev`) — use the Splunk-familiar abbreviation.

## Realistic Values for ThousandEyes (HTTP test R9→google.com)

- `response_time_ms`: daily_min=120, daily_max=200 (includes app layer overhead)
- `network_latency_ms`: daily_min=50, daily_max=80 (pure network RTT, similar to TWAMP rt_dp50)
- `throughput_kbps`: ~4.8-5.8 kbps (tiny fixed payload — NOT a load test), peak_rate 0.7 (business) to 0.9 (midnight)
- `network_latency_ms` peak_rates are **inversely correlated** with `throughput_kbps` peak_rates
- `outlier_probability = 0.0001` (very rare), outlier range 250-400ms for response_time

## Data Generation Architecture

Two separate scripts (not one):

**`bin/backfill_log.py`** — runs once at app start (when gated by `launcher.py`); writes spool payload files for the backfill window to **app spool paths** under `var/spool/ai_lab/...` for `monitor://` inputs to pick up. Output wire format follows sample extension (`.json` -> NDJSON, `.txt`/`.csv`/`.xml` -> matching text payload). Timestamps in payloads follow the `{{timestamp}}` / sample template rules (region-local wall time where applicable). **Ingestion is file-based, not HEC** for the shipped streams.

**`bin/live_log.py`** — runs continuously, writes real-time events to the same spool/monitor model from `app_start_time` onward, and applies scenario fault windows when implemented.

## File monitor inputs: CRC, `crcSalt`, and spool files

**Problem:** The forwarder’s initial CRC is derived from the **first 256 bytes** of a file. Template-based outputs with identical leading bytes can **collide** across different filenames, so the tailer may skip a file (see `_internal` TailReader / initcrc errors).

**Approach in this app (no `initCrcLength` in `props.conf` for this):**

1. **`crcSalt = <SOURCE>`** in each `monitor://` stanza in `default/inputs.conf` — the **literal** string `<SOURCE>` (angle brackets included), per Splunk’s spec, so the CRC includes the **full path** of the file and distinct paths do not look like the same file under different names.
2. **Unique spool filenames** — `backfill_log.py` names each output file with a high-resolution time component and PID so each run produces a new basename (see `docs/project_script_design.md`).

A **static** `crcSalt` string shared by all files in a path does not fix header collisions between two different new files. Use `<SOURCE>`, or tune `initCrcLength` only as a separate product-level decision (not the default approach documented here).

## Timestamp extraction (`_time`) and JSON

- **`[cisco:thousandeyes:metric]`** — `default/props.conf` uses `TIME_PREFIX` / `TIME_FORMAT` with the leading raw JSON for the top-level `timestamp` key so `_time` matches the event string from `backfill_log.py` (see `samples/thousandeyes/cisco:thousandeyes:metric/README.md`).
- **`[cnc_interface_counter_json]`** — nested `latest_data.timestamp` strings; `TIME_PREFIX` / `TIME_FORMAT` in `default/props.conf` target the indexed JSON / raw pattern for this sourcetype (see `samples/telemetry/cnc_interface_counter_json/README.md`).
- **`[cnc_srte_path_json]`** — multi-object `.txt` payloads are broken into per-object events via `LINE_BREAKER`; `TIME_PREFIX` / `TIME_FORMAT` extract per-event `_time`; host metadata is set at index time through `TRANSFORMS-set_host = set_host_from_cnc_srte_path_json` in `props.conf` and `DEST_KEY = MetaData:Host` transform in `default/transforms.conf`, with regex extraction from payload `vlan`.

After changing `props.conf` or `inputs.conf`, **reload** or restart Splunk so forwarders read the new settings.

## Scenario Control Stanza (`[scenarios]`)

Scenario runtime control values are stored in `[scenarios]`:

```ini
[scenarios]
scenario_1_activated = 0
scenario_1_fault_start = 0
scenario_1_fault_duration = 0
```

- `scenario_1_activated`:
  - `0` means inactive
  - non-zero means activation epoch time (seconds)
- `scenario_1_fault_start`: minutes after `scenario_1_activated` when fault begins
- `scenario_1_fault_duration`: minutes the fault state remains active

`scenario_1_recovery_duration` is not used in the current design to keep implementation simpler.

## Scenario Override Policy

- Keep `[baseline]` as the single source of truth for normal-state values.
- In `[scenario_*]`, define only values that must change during the fault.
- If a key is not defined in `[scenario_*]`, generator behavior falls back to baseline.
- For Scenario 1 specifically:
  - TWAMP slices `1002/1003` carry immediate fault signal.
  - `cnc_interface_counter_json` uses explicit immediate-gap keys for `R5->R7`, plus slice-based reroute keys (from/to slices, percent, start delay, and ramp).
  - ThousandEyes metrics are scenario-overridden at activation, and `response_time_ms` may return to baseline via `back_to_baseline_start_minutes` + `back_to_baseline_ramp_minutes`.
- **`cnc_service_health_json`**: during **`scenario_1`**, degraded status/score placeholders apply each tick without setting `telemetry#cnc_service_health_json#scenario_happening_probability` — **`live_log.py`** defaults that key to **`1`** when omitted (see `docs/project_scenario_1.md`).

### Scenario 1 dynamic control keys (current pattern)

Example keys in `[scenario_1]`:

```ini
telemetry#cnc_interface_counter_json#immediate_gap_out_key = R5_HundredGigE0_0_2_0_ifOutPktsRate
telemetry#cnc_interface_counter_json#immediate_gap_in_key = R7_HundredGigE0_0_0_1_ifInPktsRate
telemetry#cnc_interface_counter_json#immediate_gap_pct = 30

telemetry#cnc_interface_counter_json#reroute_from_slice = 1002,1003
telemetry#cnc_interface_counter_json#reroute_to_slice = 1001,1004
telemetry#cnc_interface_counter_json#reroute_pct = 50
telemetry#cnc_interface_counter_json#reroute_start_minutes = 3
telemetry#cnc_interface_counter_json#reroute_ramp_minutes = 7

thousandeyes#cisco:thousandeyes:metric#response_time_ms.back_to_baseline_start_minutes = 3
thousandeyes#cisco:thousandeyes:metric#response_time_ms.back_to_baseline_ramp_minutes = 7
```

### Router traffic range guidance (scenario_1 reroute path)

To keep reroute-path visuals and conservation math realistic, baseline `cnc_interface_counter_json`
rates on the core reroute chain should stay in the same magnitude band (not single-digit outliers):

- High direction (core forward band): `2222` pps, with `daily_min=1999.8`, `daily_max=2444.2`
  - Path links: `R8->R6`, `R7->R6`, `R6->R4`, `R4->R2`
- Return direction (core reverse band): `1340` pps, with `daily_min=1206`, `daily_max=1474`
  - Path links: `R6->R8`, `R6->R7`, `R4->R6`, `R2->R4`

Design intent:

- Prevent tiny baseline values on `R6-R4` / `R4-R2` from hiding reroute effects.
- Keep path segments visually consistent for workshop storytelling.
- Preserve directional asymmetry while maintaining coherent end-to-end traffic magnitude.

## Sample Directory Structure

```
samples/
└── <index>/
    └── <sourcetype>/
        ├── README.md      # placeholder docs and conventions
        └── sample.<ext>   # example template with {{placeholders}} (json/txt/csv/xml)
```
