---
name: Workshop Scenario #1 — WDM Transponder Fault
description: Details of the first (and currently only) workshop demo scenario
type: project
originSessionId: 023ba004-a2ab-41d3-9152-4eb0746bfa20
---
# Scenario #1: WDM Transponder Fault on R5-R7

**Fault:** 30% packet drop on WDM transponder between R5-NCS55A2 (Ballarat) and R7-NCS560 (Bendigo).

**Affected VLANs:** 1002 and 1003 (both share the physical R5-R7 link).

**Failover:** SR-TE detects degradation and reroutes VLAN 1002/1003 to the R9→R8→R6→R4→R2 path (VLAN 1001's path).

**Impact timeline:**
1. Normal → fault begins
2. Telemetry/TWAMP show degradation on VLAN 1002/1003 (brief window, seconds to a few minutes)
3. SR-TE reroutes → telemetry path behavior and TWAMP recover
4. TWAMP is the primary indicator (R2↔R9 on VLANs 1002/1003)
5. ThousandEyes is expected to be **mostly** stable in this scenario (resilient end-to-end path remains available). **`[scenario_1]`** still applies a **small** HTTP / network-latency uplift and slight throughput dip so charts show a minor E2E effect without dominating the story.

**Conf settings (in `default/ai_lab_scenarios.conf`):**
```ini
[scenario_1]
title = WDM Transponder Fault on R5-R7
fault_start = 0          # minutes after scenario trigger
fault_duration = 0       # minutes how long to keep the fault, 0 means the fault will remains till the scenario is deactivated
```

**App is designed to be expandable** — more scenarios will be added later. Use router names (R2-R9) as canonical identifiers, not location names.

**How to apply:** When building or extending scenarios, remember TWAMP is the primary detection mechanism, TE is secondary (short-term only due to SR-TE failover).

## Telemetry Modeling Decisions (Scenario 1)

- Fault is directional on the impaired segment: `R5 -> R7` (Ballarat toward Bendigo on the shared R5–R7 circuit).
- Do not use per-hop multiplicative growth (avoid avalanche behavior).
- On the **faulted hop only** (**`R5_HundredGigE0_0_2_0` ifOut → `R7_HundredGigE0_0_0_1` ifIn**), model loss as **`R7 ifIn` depressed below baseline** while **`R5 ifOut` follows normal baseline** (do not uplift sender rate — uplifts read as higher throughput on In/Out comparison charts instead of a receive gap). The **R9→R7** link is not the impaired span; scenario telemetry must not raise `R9` ifOut just to add “stress” or unrelated panels show a spurious step-up.
- Represent link loss explicitly using that pair mismatch. Baseline generation enforces **at most ~1%** modeled drop per link via `telemetry#cnc_interface_counter_json#directional_min_receive_fraction = 0.99`. **`[scenario_1]`** sets that fraction to **`0`** so live generation does not clamp the peer `ifIn` up toward `ifOut`; the depressed **`R7_HundredGigE0_0_0_1_ifInPktsRate`** produces the visible gap in `telemetry_if_counter_test` / the imported dashboard.
- After SR-TE steers traffic onto the **VLAN 1001** path (**R9→R8→R6→R4→R2**), **`[scenario_1]`** raises packet rates on that chain’s modeled interfaces by **~15%** vs baseline (paired directions scaled together). Live generation does not separate pre- vs post-reroute clock phases yet, so the workshop view is an illustrative **combined** fault + bypass-load profile during the active scenario window.

## TWAMP Correlation Decisions (Scenario 1)

- TWAMP loss behavior must be correlated with `cnc_interface_counter_json` directional packet-rate gaps for affected VLANs (`1002`, `1003`) during the same tick window.
- Do not model TWAMP loss independently when scenario loss is active; derive TWAMP `ul_rxpkts`/`ul_lostpkts` from the same per-tick loss context used for telemetry directional gap behavior.
- **`[scenario_1]`** sets `twamp#pca_twamp_csv#slice1002_*_rxpkts_drop_rate` and `slice1003_*_rxpkts_drop_rate` (**ul/dl/rt**) to **0.3** (flat) so each 60s window reflects **~30%** loss, matching the transponder fault headline. Generators then set `*_lostpkts` and `*_lostperc` from **`expected − rx`** (`lostperc` as **integer percent 0–100**, e.g. **30** for 30% loss).
- For the **same slices (1002/1003)**, **`[scenario_1]`** scales all baseline **TWAMP delay/jitter / delay-variation** keys—**`ul_`**, **`dl_`**, and **`rt_`**—including **`metric`**, **`daily_min`**, and **`daily_max`** where present, by **×1.2** (~**20%** higher stress than baseline). Keys that are **0** in baseline stay **0**.
- TWAMP UL packet sequence continuity must hold per slice/session:
  - `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
  - no-loss expectation: `ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
- For workshop assumptions, packet-rate style fields are interpreted as packets per second (pps); window-level expected packets are computed as `pps * window_seconds`.

## Service health (`cnc_service_health_json`)

- For VLAN **1002** and **1003**, the **sr_policy** row on **R9-NCS540** uses **`{{impacted_sre_policy_health_status}}`** and **`{{impacted_sr_policy_health_score}}`**. Baseline: **`SERVICE_UP`** / **100**; **`[scenario_1]`** overlays **`SERVICE_DEGRADED`** / **50**. You do **not** need to set **`telemetry#cnc_service_health_json#scenario_happening_probability`**: `live_log.py` treats a missing or invalid value as **`1`**, so scenario keys apply on every eligible emission during the fault window (use a fractional value only when you want stochastic fallback to baseline for this sourcetype).
