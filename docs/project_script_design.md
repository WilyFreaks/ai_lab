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
2. If `backfill_start_time` is set to 0, or not set,
   - Set `backfill_start_time` to the current epoch time
   - Set `backfill_completed = false`
   - Write to `local/ai_lab_scenarios.conf`
3. Spawn `backfill_log.py` as a subprocess
4. Spawn `live_log.py` as a subprocess

---

## backfill_log.py

**Invoked by:** `launcher.py`

**Runs:** Once — exits when backfill is complete.

**Responsibilities:**
1. Read `backfill_start_time` and `backfill_days` from conf
2. If `backfill_completed = true`, exit immediately (already done)
3. Generate synthetic events at configured intervals for the window:
   `(backfill_start_time - backfill_days)` → `backfill_start_time`
4. Send events to Splunk HEC with historical timestamps
5. On completion, write `backfill_completed = true` to `local/ai_lab_scenarios.conf`

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
2. Generate synthetic events at configured intervals, sending to Splunk HEC with current timestamps
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

---

## State in local/ai_lab_scenarios.conf

```ini
[baseline]
backfill_start_time = 0
backfill_completed  = false

[scenarios]
scenario_1_activated = 0
scenario_1_fault_start = 0
scenario_1_fault_duration = 0
```

- Written by `launcher.py` (initial set) and `backfill_log.py` (completion flag)
- Never written to `default/ai_lab_scenarios.conf` — runtime state only

## Scenario Activation Path

- Dashboard view (`scenario_control`) executes custom search command `scenariocontrol`.
- Command script `bin/scenario_control.py` writes scenario runtime values to `local/ai_lab_scenarios.conf`.
- Activation behavior:
  - Enable: set `<scenario>_activated` to current epoch time
  - Disable: set `<scenario>_activated` to `0`
