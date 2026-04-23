---
name: Dashboard Design Decisions
description: Design and behavior of workshop dashboards, including region selection persistence
type: project
originSessionId: 023ba004-a2ab-41d3-9152-4eb0746bfa20
---
# Dashboard Design

## Overview

This document defines the dashboard layer for `ai_lab`, with focus on:

- `scenario_control` for scenario runtime control
- `workshop_introduction` for region selection and workshop context

The dashboard tier is intentionally thin. Runtime state is persisted through custom search commands into `local/ai_lab_scenarios.conf`.

---

## Navigation

Defined in `default/data/ui/nav/default.xml`.

Current dashboard entries include:

- `scenario_control`
- `workshop_introduction`

`search` remains the search view target for ad-hoc SPL.

---

## Workshop Introduction Dashboard

View file: `default/data/ui/views/workshop_introduction.xml`

### Primary goals

1. Show workshop context image (`data_sources.jpg`)
2. Allow user to choose region (`au` or `jp`)
3. Persist selected region to local runtime config
4. Open the baseline generation gate and trigger launcher
5. Load persisted region and readiness state when dashboard opens

### Visual components

- Form title: **Workshop Introduction**
- Dropdown input:
  - token: `region`
  - choices: `au`, `jp`
- Image panel:
  - `/static/app/ai_lab/data_sources.jpg`
- Save result panel:
  - table search used as write feedback for command output (`set` action)
- Readiness panel:
  - shows region readiness, generation gate state, and backfill state

### Startup/load behavior

At load, dashboard runs:

```spl
| workshopregion action="status"
```

Returned fields are mapped into dashboard tokens:

- `region`
- `region_ready`
- `baseline_generation_enabled`
- `backfill_start_time`
- `backfill_completed`

`region` is used as dropdown default.

Fallback behavior:

- If no valid region exists in conf, default region is `au`.

### Save behavior

On form submit, dashboard runs:

```spl
| workshopregion action="set" region="$form.region$"
```

The command validates and persists the value, sets `baseline_generation_enabled=true`, and triggers `launcher.py`.
`backfill_start_time`/`backfill_completed` are not prefilled by the dashboard command; they are owned by launcher/backfill runtime.

---

## Region Persistence Model

Runtime source of truth:

- `local/ai_lab_scenarios.conf`
- stanza: `[baseline]`
- key: `region`
- key: `baseline_generation_enabled`
- initial local values are blank (or absent) until host saves region

Default/fallback source:

- `default/ai_lab_scenarios.conf`
- stanza: `[baseline]`
- key: `region`

Selection precedence in runtime logic:

1. local value (if present and valid)
2. default value (if present and valid)
3. fallback hard default: `au`

Valid values are strictly:

- `au`
- `jp`

---

## Custom Command Integration

Command stanza in `default/commands.conf`:

```ini
[workshopregion]
filename = workshop_region.py
chunked = false
generating = true
local = true
```

Implementation file: `bin/workshop_region.py`

Supported actions:

- `action=get`
  - returns current effective region
- `action=status`
  - returns effective region + readiness/generation state
- `action=set region=<au|jp>`
  - writes region to local conf, sets generation gate to true, and triggers launcher

Why command-based persistence:

- Keeps write logic server-side and app-scoped
- Avoids direct file operations from dashboard XML
- Provides input validation and explicit response payload
- Allows safe server-side trigger of launcher when workshop host confirms region

---

## Scenario Control Dashboard Notes

View file: `default/data/ui/views/scenario_control.xml`

Design constraints:

- Uses form submit mode (`submitButton="true"`) to avoid writes on page load
- Input token names omit `form.` prefix (required for deferred submit behavior)
- Write operation runs only after submit via `scenariocontrol`

This pattern is reused in workshop-introduction save flow.

---

## Static Asset Convention

Images must be placed under:

- `appserver/static/`

Referenced in dashboards via:

- `/static/app/ai_lab/<filename>`

Current workshop image:

- `data_sources.jpg`

---

## Extension Plan

To scale to more regions:

1. Extend `VALID_REGIONS` in `workshop_region.py`
2. Add dropdown choices in `workshop_introduction.xml`
3. Add region-specific workshop assets in `appserver/static/`
4. Optionally add dynamic image selection by region token

To add read-only intro content without write behavior:

- keep `action=get` load search
- remove save panel and submit flow

