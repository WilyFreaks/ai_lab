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
1. Normal -> fault begins
2. Immediate fault signal:
   - TWAMP 1002/1003 loss/stress applies immediately.
   - Telemetry `R5 -> R7` directional Out/In gap applies immediately (30% receive-side depression on `R7` peer `ifIn` vs `R5` `ifOut`).
3. Reroute control plane delay (`telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes`) elapses.
   - IOS BFD/control-plane fault sequence (`samples/ios/cisco:ios/sample_bfd.txt`) is emitted at this reroute-start point to indicate BFD detection and SR-policy impact timing.
4. Telemetry reroute ramps over `telemetry#cnc_interface_counter_json#sample.json#reroute_ramp_minutes`:
   - `reroute_from_slice` traffic decreases.
   - removed volume is redistributed to `reroute_to_slice` (conserved shift; not independent +pct on healthy slices).
5. ThousandEyes response-time uplift starts at scenario activation, then returns to baseline using:
   - `thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_start_minutes`
   - `thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_ramp_minutes`

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

- Fault is directional on the impaired segment: `R5 -> R7`.
- Immediate directional gap behavior is explicit and independent from reroute timing:
  - out key: `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_out_key = R5_HundredGigE0_0_2_0_ifOutPktsRate`
  - in key: `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_in_key = R7_HundredGigE0_0_0_1_ifInPktsRate`
  - gap percent: `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_pct = 30`
- Link-direction conservation clamp policy:
  - baseline uses `telemetry#cnc_interface_counter_json#sample.json#directional_min_receive_fraction = 0.99`
  - scenario uses `telemetry#cnc_interface_counter_json#sample.json#directional_min_receive_fraction = 0` so intentional gap effects are not clamped away.
- Reroute is slice-based (not per-interface scenario targets):
  - `telemetry#cnc_interface_counter_json#sample.json#reroute_from_slice = 1002,1003`
  - `telemetry#cnc_interface_counter_json#sample.json#reroute_to_slice = 1001,1004`
  - `telemetry#cnc_interface_counter_json#sample.json#reroute_pct = 50`
  - `telemetry#cnc_interface_counter_json#sample.json#reroute_start_minutes` delay before reroute starts
  - `telemetry#cnc_interface_counter_json#sample.json#reroute_ramp_minutes` ramp to full reroute
- `reroute_pct` semantics: remove `%` from from-slices and redistribute removed volume to to-slices by baseline-weight share. This is a conserved shift, not "increase healthy slices by their own +%".
- Baseline reroute-path traffic ranges should remain core-consistent so reroute effects are visible on each hop:
  - forward-band links (`R8->R6`, `R7->R6`, `R6->R4`, `R4->R2`): around `2222` pps (`daily_min=1999.8`, `daily_max=2444.2`)
  - reverse-band links (`R6->R8`, `R6->R7`, `R4->R6`, `R2->R4`): around `1340` pps (`daily_min=1206`, `daily_max=1474`)

## TWAMP Correlation Decisions (Scenario 1)

- TWAMP loss behavior must be correlated with `cnc_interface_counter_json` directional packet-rate gaps for affected VLANs (`1002`, `1003`) during the same tick window.
- Do not model TWAMP loss independently when scenario loss is active; derive TWAMP `ul_rxpkts`/`ul_lostpkts` from the same per-tick loss context used for telemetry directional gap behavior.
- **`[scenario_1]`** sets `twamp#pca_twamp_csv#sample.csv#slice1002_*_rxpkts_drop_rate` and `twamp#pca_twamp_csv#sample.csv#slice1003_*_rxpkts_drop_rate` (**ul/dl/rt**) to **0.3** (flat) so each 60s window reflects **~30%** loss, matching the transponder fault headline. Generators then set `*_lostpkts` and `*_lostperc` from **`expected − rx`** (`lostperc` as **integer percent 0–100**, e.g. **30** for 30% loss).
- For the **same slices (1002/1003)**, **`[scenario_1]`** scales all baseline **TWAMP delay/jitter / delay-variation** keys—**`ul_`**, **`dl_`**, and **`rt_`**—including **`metric`**, **`daily_min`**, and **`daily_max`** where present, by **×1.2** (~**20%** higher stress than baseline). Keys that are **0** in baseline stay **0**.
- TWAMP UL packet sequence continuity must hold per slice/session:
  - `next ul_firstpktSeq = previous ul_lastpktSeq + 1`
  - no-loss expectation: `ul_rxpkts = (ul_lastpktSeq - ul_firstpktSeq) + 1`
- For workshop assumptions, packet-rate style fields are interpreted as packets per second (pps); window-level expected packets are computed as `pps * window_seconds`.

## ThousandEyes behavior (Scenario 1)

- Scenario applies an initial response-time/latency uplift at activation.
- `response_time_ms` supports explicit return-to-baseline timing:
  - `thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_start_minutes`
  - `thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_ramp_minutes`
- During `back_to_baseline_start_minutes`, scenario response-time uplift stays active.
- After that delay, response-time linearly returns to baseline over `back_to_baseline_ramp_minutes`.

## Service health (`cnc_service_health_json`)

- For VLAN **1002** and **1003**, the **sr_policy** row on **R9-NCS540** uses **`{{impacted_sre_policy_health_status}}`** and **`{{impacted_sr_policy_health_score}}`**. Baseline: **`SERVICE_UP`** / **100**; **`[scenario_1]`** overlays **`SERVICE_DEGRADED`** / **50**. You do **not** need to set **`telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability`**: `live_log.py` treats a missing or invalid value as **`1`**, so scenario keys apply on every eligible emission during the fault window (use a fractional value only when you want stochastic fallback to baseline for this sourcetype).
