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
2. VLAN 1002/1003 show packet loss + high latency (brief degradation window, seconds to a few minutes)
3. SR-TE reroutes → TE and TWAMP recover
4. TWAMP is the primary indicator (R2↔R9 on VLANs 1002/1003)
5. TE shows only short-term degradation before SR-TE kicks in

**Conf settings (in `default/ai_lab_scenarios.conf`):**
```ini
[scenario_1]
title = WDM Transponder Fault on R5-R7
fault_start = 20          # minutes after scenario trigger
fault_duration = 2
recovery_duration = 10
fault_link_src = R7-NCS560
fault_link_dst = R5-NCS55A2
affected_vlans = 1002,1003
failover_vlan = 1001
```

**App is designed to be expandable** — more scenarios will be added later. Use router names (R2-R9) as canonical identifiers, not location names.

**How to apply:** When building or extending scenarios, remember TWAMP is the primary detection mechanism, TE is secondary (short-term only due to SR-TE failover).
