# 5G WDM backbone - failure detection, correlation, and recovery guidance

## Purpose

Guide a **structured Splunk investigation** from service-level symptoms through **ThousandEyes**, **alerts / episodes**, **TWAMP**, **SR-TE / path context**, **telemetry**, **IOS**, and **WDM** (PM + syslog) sources. Output is **evidence-led**; treat definitive "root cause" statements as a **debrief** option when the user asks or when the chain is unambiguous in the data.

**Prerequisites:** follow **`rules_en.md`** (MCP, saved-search-first, data contracts, `local/` policy).

---

## Topology (logical)

```text
R8 -- R6 -- R4 -- R2
|     |           |
R9 -- R7 -- R5 -- R3
```

- **Routers:** R2-R9 (Cisco NCS family in the workshop narrative).
- **Protocols (narrative):** SR-MPLS, IS-IS, BFD, BGP; **SR-TE** policies per slice / VLAN (commonly **1001-1004** in docs).
- **Management addressing (lab fiction):** e.g. `172.20.0.{2..9}` ↔ `R{2..9}` when the scenario uses that map.
- **Regional lookups:** AU dashboards use **`router_areas_au.csv`**; JP uses **`router_areas_jp.csv`** - do not cross-wire.

---

## Data sources (where to look)

| Domain | Typical index / sourcetype | Notes |
|--------|---------------------------|--------|
| ThousandEyes | `index=thousandeyes` | End-to-end synthetic; watch **seconds vs ms** when comparing to conf. |
| TWAMP | `index=twamp` `sourcetype=pca_twamp_csv` | **`ul_lostperc` / `dl_lostperc` = 0-100 integer %**; correlate with telemetry on shared links (e.g. VLAN **1002/1003**). |
| Telemetry | `index=telemetry` `sourcetype=cnc_interface_counter_json` | Per-interface counters; use **`telemetry_if_counter`** and IF-rate saved searches when possible. |
| SR-TE path | `index=telemetry` `sourcetype=cnc_srte_path_json` | Active hops / policy results per host-slice. |
| IOS | `index=ios` | BFD, IS-IS, SR-TE policy UPDOWN, link events - correlate timestamps with TWAMP/telemetry. |
| WDM syslog | `wdm_alert`, `wdm_pm`, etc. | **`wdm_alert`**: fault XML; host from EMS alias contract. **`wdm_pm`**: transponder PM; bind **`router_wdm_transponders.csv`**. |
| Scenario alerts | `index=alerts` `sourcetype=ai_lab_alert` | Materialized alert rows from scheduled searches. |
| Episodes | `index=episode` (if populated) | Higher-level rollups when the workshop enables them. |

---

## Global execution rules

1. At the **start of each step**, print one status line:

   ```text
   * Step X running: <short description>
   ```

2. At the **end of each step**, print a **short summary** (facts + timestamps) and the **next step** (or "stop - insufficient data").

3. **Before ad hoc SPL**, list relevant **`| savedsearch`** names in **`ai_lab`** (`default/savedsearches.conf` / local overrides). Prefer saved searches over reinventing SPL.

4. **Time window:** use **last 60 minutes** unless the user specifies another range; repeat Step 1 after recovery narrative to show **post-change** ThousandEyes.

5. **Compact mode:** if the user asks to skip banners, keep step boundaries in headings only.

---

## Step 1 - ThousandEyes (service monitor)

**Status line:** `* Step 1 running: ThousandEyes service monitor (last ~60m)...`

**Action**

- Prefer: `| savedsearch thousandeyes_response_time_sec` with CLI/API window **`-60m` → `now`** (or equivalent in MCP).
- If you need a custom chart: `index=thousandeyes sourcetype=cisco:thousandeyes:metric` (or the sourcetype your deployment uses), `bin _time span=1m`, `stats avg(response_time_sec)` (or the field the saved search uses).

**Interpretation**

- Mark **degradation** when recent `avg(response_time_sec)` (or workshop-defined bound from saved search / scenario) exceeds the **expected band** for the window.
- Record **`_time`** of the first sustained breach as **detection time** for downstream correlation.

---

## Step 2 - Alerts and episode-style correlation

**Status line:** `* Step 2 running: Alerts / episode correlation...`

**Action**

1. If **`list_episodes`** (or similarly named) exists as an **`ai_lab`** saved search, run `| savedsearch list_episodes` in the user's time window.
2. Otherwise, query **`index=alerts sourcetype=ai_lab_alert`** (and **`index=episode`** if populated) with explicit `earliest`/`latest`.

**Interpretation**

- Treat **Critical** escalation on **Interface counter mismatch**-class alerts as **strong data-plane evidence** in this workshop.
- Do **not** assert optical vs router root cause here; use later IOS + WDM correlation.

---

## Step 3 - TWAMP quality (slices / sessions)

**Status line:** `* Step 3 running: TWAMP loss / delay / jitter per slice...`

**Action (patterns - prefer tightening fields to your column set)**

```spl
index=twamp sourcetype=pca_twamp_csv earliest=-60m latest=now
| head 5000
| fields _time "Session Name" Interface ul_lostperc dl_lostperc ul_dmean dl_dmean rt_dmean rt_jmean
```

**Interpretation**

- **`ul_lostperc` / `dl_lostperc`** are **already 0-100 % integers** - do **not** divide by 10 000.
- Slice/session: parse from **`Session Name`** (e.g. `Slice1002`) with `rex` when needed.
- Relate worst slices to **SR-TE** and **telemetry** in later steps.

---

## Step 4 - Path mapping (degraded vs healthy)

**Status line:** `* Step 4 running: Compare degraded vs healthy slice paths...`

**Action**

- Join TWAMP session / slice identifiers with **`cnc_srte_path_json`** (hops, policy results) using **`index=telemetry`** and the workshop's host/slice naming.
- Goal: list **routers / hops** that appear only on **bad** slice paths or show divergent loss/delay.

---

## Step 5 - Telemetry interface verification

**Status line:** `* Step 5 running: Telemetry interface loss / mismatch signals...`

**Action**

- Prefer `| savedsearch telemetry_if_counter` (time window as above).
- Example filter for **high drop** (adjust threshold if the facilitator requests):

```spl
| savedsearch telemetry_if_counter
| where r1_to_r2_drop_rate > 30 OR r2_to_r1_drop_rate > 30
```

**Interpretation**

- Use **directional** columns from the saved search output; align with **TWAMP** direction and **SR-TE** hop direction when narrating.

---

## Step 6 - IOS events (control plane)

**Status line:** `* Step 6 running: IOS logs (BFD, IS-IS, SR-TE policy)...`

**Action**

```spl
index=ios earliest=-60m latest=now
| sort _time
| table _time host _raw
```

Optional narrow filter (expand per workshop IOS patterns):

```spl
index=ios earliest=-60m latest=now
(_raw=*BFD* OR _raw=*IS-IS* OR _raw=*SR*POLICY* OR _raw=*ADJCHANGE*)
| table _time host _raw
```

**Interpretation**

- Align **DOWN / adjacency loss / policy change** timestamps with **Step 1** detection time and **Step 3** TWAMP degradation.

---

## Step 7 - WDM (PM saved searches + syslog)

**Status line:** `* Step 7 running: WDM PM / syslog vs suspected routers...`

**Action - use these `ai_lab` saved searches (names as shipped; `_by_router` variants preferred)**

| Saved search | Interpretation hint |
|--------------|---------------------|
| `wdm_LSBIASCUR_over_time_by_router` | Laser bias - **Tx-side** stress / aging signal (contextual). |
| `wdm_FEC_BEF_COR_ER_over_time_by_router` | FEC pre-correction - treat as **Rx-side** optical / transponder quality indicator. |
| `wdm_LOSTOPCUR_over_time_by_router` | Lost optical power current - **optical path / Tx-Rx** context (workshop narrative). |
| `wdm_BDTEMPCUR_over_time_by_router` | Board temperature - thermal / hardware stress. |
| `wdm_EDTMPCUR_over_time_by_router` | EDFA-related current - amplifier path narrative. |
| `wdm_SUMOOPCUR_over_time_by_router` / `wdm_SUMIOPCUR_over_time_by_router` | **Tx / Rx** optical power summaries when present. |

Also search **`wdm_alert`** / relevant **syslog** sourcetypes for **fault text** near the same **host** and **time**.

**Interpretation**

- Tie PM endpoints to routers using **`router_wdm_transponders.csv`** and the workshop A/Z columns - do not invent cross-links.

---

## Step 8 - Forecasting (optional, for ML/anomaly demo)

**Status line:** `* Step 8 running: Forecasting (anomaly context / ML demo)...`

**When to use:** facilitator asks for a prediction view, anomaly framing, or ML demo; or you need to compare actual vs expected to confirm a metric is truly anomalous.

**Action — prefer these `ai_lab` forecasting saved searches:**

| Saved search | Algorithm | Scope |
|---|---|---|
| `forecast_cdtsm` | CDTSM | ThousandEyes response time (single series, 7-day training) |
| `forecast_predict` | LLP5 seasonal | ThousandEyes response time (single series, 7-day training) |
| `forecast_cdtsm_multi_series` | CDTSM | Per-interface in-packet rate, all routers (2-week training) |
| `forecast_predict_multi_series` | LLP5 seasonal | Per-interface in-packet rate, all routers (2-week training) |

All return actual + prediction + confidence bounds (last 60 points). Use `forecast_cdtsm` / `forecast_predict` for the UX angle and `*_multi_series` for the traffic angle.

**CDTSM model context (xc and xf):** CDTSM takes two resolution inputs — **xf** (fine context, up to 512 points at your data granularity) and **xc** (coarse context, up to 512 points at 60× the fine resolution). For 1-minute data: xc = 1-hour resolution; for 5-minute: xc = 5-hour. Recommended granularity: **1, 2, 3, or 4 minutes** (divides 1440 evenly for clean daily seasonality). Practical maximum training window: **~40 days**. Both contexts must align at the same end-point in time.

**For a focused per-router view:** use the **parameterized** saved search `cnc_interface_ifInPktsRate_for_a_router` with argument `router="R2"` — narrows the chart to that router's interfaces only. **Note:** this search is currently disabled in the workshop environment; use `cnc_interface_ifInPktsRate` (all routers) as the alternative.

**Interpretation**

- Compare actual values with prediction bounds during the fault window to quantify how far out-of-band behavior was.
- Present to attendees as "Splunk's ML flagging the anomaly before the alert fired."

---

## Closing - hypotheses, actions, recovery check

1. Summarize **three bullets**: (a) strongest **service** evidence, (b) strongest **packet/path** evidence, (c) strongest **L1/optical vs router** evidence - label confidence (high/medium/low).
2. **Remediation:** only **recommend** actions (escalation, ticket fields, lab "SR-TE bypass" narrative) - no pretend CLI to production.
3. **Recovery validation:** rerun **Step 1** ThousandEyes view; confirm **improved** response-time behavior **if** the scenario timeline includes recovery.

---

## Packaging note (`default/` for Git / AMI)

Follow **`agent_rules_en.md` §5** (and `.cursor` Splunk app rules): **`savedsearches.conf`** and **`metadata` (`local.meta` / `default.meta`)** are **merged** into shipped `default/` so **default-only stanzas or keys** are not lost. **Dashboard Simple XML** is **one file per view**; on explicit user request, **full-file replace** `local/data/ui/views/<name>.xml` → `default/data/ui/views/<name>.xml` is correct.

---

## Related project files

- `docs/project_ai_lab.md` - topology, sources, WDM contracts.
- `default/savedsearches.conf` - authoritative saved search names.
- `samples/twamp/pca_twamp_csv/README.md` - TWAMP wire units.
