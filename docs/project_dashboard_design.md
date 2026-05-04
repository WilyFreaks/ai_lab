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

- `workshop_introduction`
- `scenario_control`

`search` remains the search view target for ad-hoc SPL.

Scenario dashboard navigation policy:

- Do **not** add individual scenario dashboards (for example `scenario_1_*`) as direct links in `default/data/ui/nav/default.xml`.
- Scenario dashboards are accessed from `scenario_control` only.
- The scenario link should be generated dynamically in `scenario_control` when the corresponding scenario is enabled.

### Scenario dashboard authoring: `local/` vs `default/`

During workshop iteration, scenario Simple XML is **maintained under** `local/data/ui/views/` (Splunk UI “save” targets `local`, or files are edited there directly).

The **`default/data/ui/views/`** copy is the **packaged / Git-tracked** source of truth for the same view name.

**Sync policy:**

- When the user explicitly asks to promote changes (for example “copy local dashboard to default”, “sync `scenario_1_au` from local to default”), copy **`local/data/ui/views/<view>.xml`** → **`default/data/ui/views/<view>.xml`** as a **full-file replacement**—use a single OS-level copy (`cp`), not a manual merge (same pattern as `local/savedsearches.conf` → `default/savedsearches.conf` on request).
- Agents do **not** auto-copy on every edit; wait for an explicit sync request so `local/` remains the safe edit surface.
- **Which file Splunk uses:** for the same view name, **`local/data/ui/views/` overrides `default/data/ui/views/`**. Packaging updates land in `default/`; day-to-day UI edits usually hit `local/`. Keep both in sync when promoting so Git reflects the dashboard you intend to ship.
- After a sync, **reload the dashboard** (or refresh the Splunk view) if the browser still shows older XML.

---

## Workshop Introduction Dashboard

View file: `default/data/ui/views/workshop_introduction.xml`  
JS file: `appserver/static/workshop_introduction_submit_toggle.js`

### Primary goals

1. Show workshop context image (`data_sources.jpg`)
2. Allow user to choose region (`au` or `jp`) when not yet persisted
3. Persist selected region to local runtime config
4. Open the baseline generation gate and trigger launcher
5. On load, read persisted region and show backfill status

### Visual states

**Unlocked** (region not yet persisted — `region_ready=false`):

- Fieldset (dropdown + Submit button) is visible
- Dashboard description is visible
- Dropdown input (`token=region`, choices: `au`/`jp`) is visible (`depends="$region_unlocked$"`)
- Data Sources image panel is visible

**Locked** (region persisted — `region_ready=true`):

- Fieldset, description hidden by JS (`setControlHidden(true)`)
- Data Sources image panel is visible
- Backfill status panel visible (`depends="$region_locked$"`), running `action="set"` to show result

### Startup / load behavior

At load, the JS module (`workshop_introduction_submit_toggle.js`) runs once:

1. Immediately calls `setControlHidden(true)` to suppress fieldset before status resolves (prevents slideshow flicker)
2. Dispatches `| workshopregion action="status"` via `SearchManager` (id: `region_search`, `autostart: false`)
3. On result, calls `syncFromRow(row)` which sets:
   - `region_locked=true` + unset `region_unlocked` (if `region_ready=true`)
   - `region_unlocked=true` + unset `region_locked` (if `region_ready=false`)
   - `status_region`, `status_region_ready`, `status_enabled`, `status_backfill_start`, `status_backfill_completed`, `status_backfill_duration`, `status_backfill_completed_time`, `status_backfill_run_started_time`
4. Calls `applyVisibilityFromReady()` which reads `status_region_ready` and calls `setControlHidden(true/false)`

**No baseline Simple XML `<search>` is used.** All initial state is driven by JS.

### Token architecture

| Token | Purpose | Set by |
|---|---|---|
| `region_locked` | XML `depends` for locked rows | JS `syncFromRow`, XML `<done>` |
| `region_unlocked` | XML `depends` for unlocked rows/input | JS `syncFromRow`, XML `<done>` |
| `status_region` | Display + save query parameter | JS `syncFromRow`, XML `<done>` |
| `status_region_ready` | JS visibility signal | JS `syncFromRow`, XML `<done>` |
| `status_enabled` | Display | JS `syncFromRow`, XML `<done>` |
| `status_backfill_start` | Display | JS `syncFromRow`, XML `<done>` |
| `status_backfill_completed` | Display | JS `syncFromRow`, XML `<done>` |
| `status_backfill_duration` | Backfill wall-clock duration (seconds), when complete | JS `syncFromRow`, XML `<done>` |
| `status_backfill_completed_time` | Epoch when backfill finished | JS `syncFromRow`, XML `<done>` |
| `status_backfill_run_started_time` | Epoch when backfill run started | JS `syncFromRow`, XML `<done>` |
| `region` | Form input token (dropdown) | Form selection, XML `<done>` |

Key design constraint: JS does **not** set the `region` form token on load. This prevents the save row (`depends="$region_unlocked$"`) from triggering the save search before the user explicitly selects and submits.

### `depends` and search execution

`depends` on a `<row>` controls **visual visibility only** — the panel's search still executes when its query tokens are set, even if the row is hidden.

`autoRun="false"` on `<fieldset>` defers **all** panel searches until Submit is clicked — regardless of whether their query tokens are form inputs or not. If Submit is never clicked (e.g. locked state where the fieldset is hidden), no panel search ever runs.

In locked state, JS triggers Submit programmatically after setting all tokens so the locked panel's search runs on reload:
```javascript
setTimeout(function() {
    $(".fieldset button.btn.btn-primary").trigger("click");
}, 100);
```

### Save behavior

On form Submit (unlocked state):

1. User selects `au` or `jp` from dropdown → `$region$` set in default token model
2. User clicks Submit → `$submitted.region$` set → save search runs:

```spl
| workshopregion action="set" region="$region$"
```

The `<done>` block updates all tokens:

- `status_region`, `status_region_ready`, `status_enabled`, `status_backfill_start`, `status_backfill_completed`, `status_backfill_duration`, `status_backfill_completed_time`, `status_backfill_run_started_time` from result fields
- `region_locked=true`, unset `region_unlocked` → transitions dashboard to locked state

### Locked state backfill status panel

When locked, the panel (`depends="$region_locked$"`) runs:

```spl
| workshopregion action="set" region="$status_region$"
```

This allows the user to view backfill and generation status on each dashboard load.  
`$status_region$` is used (not `$region$`) because `$region$` is intentionally unset in the locked state.

### JS visibility control (`setControlHidden`)

Controls hidden when `region_ready=true` (or unknown):

- `.fieldset button.btn.btn-primary` (Submit button)
- `a.hide-global-filters` and `.dashboard-form-globalfilters`
- `.dashboard-form-globalfieldset` (fieldset container)
- `.dashboard-header-description` (description text)

Listener: `defaultTokenModelun.on("change:status_region_ready", applyVisibilityFromReady)`

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

Selection precedence for **persisted** workshop region (`region` / `region_ready`):

1. Local `local/ai_lab_scenarios.conf` (if valid `au`|`jp`)
2. Default `default/ai_lab_scenarios.conf` (if valid)

If neither yields a valid `au`|`jp`, `region` is empty and `region_ready` is false. Backfill `*_local` timestamps use UTC in that case.

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
  - returns configured region snapshot (same family as status)
- `action=status`
  - returns configured persisted region (`region`, may be blank), `region_ready`, readiness/generation state, and backfill timing including wall-clock `backfill_run_started_time`, `backfill_completed_time`, and `backfill_duration` (seconds) when backfill has completed
- `action=set region=<au|jp>`
  - writes region to local conf, sets generation gate to true, and triggers launcher
  - returns the same core field family as `action=status` plus `launcher_triggered`, `launcher_message`, `initial_backfill`, and `region_ready: "true"` on success
  - includes backfill wall-clock fields when present in conf: `backfill_run_started_time`, `backfill_completed_time` (epochs), their `*_local` formatted variants, and `backfill_duration` (seconds) once `backfill_completed` is `true`

`effective_region` fallback (previously defaulted to `au` when unset) has been removed. If no valid region is persisted, `region` is empty and `region_ready` is `false`.

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
- Scenario-specific dashboard links are rendered dynamically from runtime scenario state, and only for enabled scenarios.

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

---

## Planned Dashboard: `scenario_1_monitor`

Goal:

- Provide a focused monitor view for `scenario_1` metric behavior during baseline and fault windows.

Validation data source policy:

- Prefer existing saved searches in app `ai_lab` as panel sources:
  - `telemetry_if_counter_test`
  - `cnc_interface_ifOutPktsRate_test`
  - `cnc_interface_ifInPktsRate_test`
  - `thousandeyes_response_time_sec_test`
  - `twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test` (TWAMP `pca_twamp_csv` health and delay/jitter bands)
- For "live is active now" checks, use a bounded recent window (recommended last 5 minutes).

Initial panel intent:

1. Telemetry directional gap/drop-rate status (`telemetry_if_counter_test`)
2. Interface outbound packet-rate trend (`cnc_interface_ifOutPktsRate_test`)
3. Interface inbound packet-rate trend (`cnc_interface_ifInPktsRate_test`)
4. ThousandEyes response-time trend (`thousandeyes_response_time_sec_test`)
5. TWAMP ingest cadence and delay/jitter sanity (`twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test`)

---

## Imported Dashboard Intake (Current Practice)

When a dashboard is copied from another Splunk environment (for example `default/data/ui/views/scenario_1_au.xml`), follow this sequence:

1. Keep the imported SPL intact first (no immediate logic rewrites).
2. If workshop owner says they will manually import/update a dashboard source, treat that import content as user-managed and do not preemptively redesign it.
3. Translate user-facing Japanese/non-English strings to English unless workshop language requires otherwise.
4. Keep scenario description text quiz-oriented (hint only), so attendees investigate root cause from panels.
5. Inventory all SPL data sources into a CSV under `docs/` with columns:
   - `index,sourcetype,source,host,time duration`
6. Treat non-`ai_lab` indexes and external script paths as legacy dependencies to be compared/migrated later.

Current inventory artifact:

- `docs/scenario_1_au_dashboard_data_sources.csv`

Migration checkpoint status:

- The Interface In/Out Packet Count Comparison panel migration is complete for `scenario_1_au`.
- Next runtime checkpoint before dashboard validation:
  - generate `twamp`
  - generate `telemetry#cnc_srte_path_json`
  - generate `telemetry#cnc_interface_counter_json`
