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

**`bin/backfill_log.py`** — runs once at app start, generates `(app_start_time - backfill_days)` to `app_start_time`, sends to Splunk HEC with historical timestamps.

**`bin/live_log.py`** — runs continuously, generates real-time events from `app_start_time` onward, listens for scenario trigger to switch to fault values.

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
- For Scenario 1 specifically, ThousandEyes metrics can remain unchanged while telemetry/TWAMP and CNC-path *fields* (for example `cnc_srte_path_json`) carry the fault signal.

## Sample Directory Structure

```
samples/
└── <index>/
    └── <sourcetype>/
        ├── README.md      # placeholder docs and conventions
        └── sample.json    # example log template with {{placeholders}}
```
