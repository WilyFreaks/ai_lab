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
5. ThousandEyes is expected to be mostly stable in this scenario (resilient end-to-end path remains available)

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

- Fault is directional on the impaired segment: `R7 -> R5`.
- Do not use per-hop multiplicative growth (avoid avalanche behavior).
- Apply bounded forward-path increase on affected VLAN flow:
  - `R7` highest increase
  - `R9` lower than `R7`
  - downstream routers smaller uplift
- Represent link loss explicitly using interface pair mismatch on faulted direction (e.g., `R7 ifOut` vs `R5 ifIn`).
