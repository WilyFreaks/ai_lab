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
2. If `backfill_start_time` is not set:
   - Set `backfill_start_time = now`
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
3. Generate synthetic events for the window:
   `(backfill_start_time - backfill_days)` → `backfill_start_time`
4. Send events to Splunk HEC with historical timestamps
5. On completion, write `backfill_completed = true` to `local/ai_lab_scenarios.conf`

**Restart behavior:** If Splunk restarts mid-backfill, `backfill_start_time` is already set in `local/`, so the same time window is used — no duplicate or missing data.

---

## live_log.py

**Invoked by:** `launcher.py`

**Runs:** Continuously until Splunk stops.

**Responsibilities:**
1. Read `backfill_start_time` from conf as the real-time anchor
2. Generate synthetic events at configured intervals, sending to Splunk HEC with current timestamps
3. Listen for scenario trigger (mechanism TBD)
4. On trigger, switch metric values to fault-state values defined in `[scenario_1]`
5. After `fault_duration`, transition to recovery; after `recovery_duration`, return to baseline

---

## Production Data Quality Requirements

- Weekend/weekday transitions must be smooth in production generation logic.
- Do not introduce abrupt step changes at boundary hours (especially Sunday 22:00-23:59 JST).
- Apply interpolation windows around Fri→Sat and Sun→Mon transitions so chart behavior stays realistic.

---

## State in local/ai_lab_scenarios.conf

```ini
[baseline]
backfill_start_time = 2026-04-21T09:00:00Z
backfill_completed  = true
```

- Written by `launcher.py` (initial set) and `backfill.py` (completion flag)
- Never written to `default/ai_lab_scenarios.conf` — runtime state only
