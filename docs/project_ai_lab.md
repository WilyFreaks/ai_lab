---
name: AI Lab Splunk App — Project Context
description: Purpose, network topology, router mapping, and data sources for the AI Lab workshop app
type: project
originSessionId: 023ba004-a2ab-41d3-9152-4eb0746bfa20
---
# AI Lab Splunk App

**Purpose:** Splunk custom app for a workshop to introduce Splunk's AI capabilities to customers. Runs as an AWS AMI spun up ~1 hour before the workshop starts.

**GitHub repo:** https://github.com/WilyFreaks/ai_lab (public, owner: wilyfreaks / WilyFreaks)

**Why:** Workshop demo that needs to be portable — same app can be reused for different countries (AU, JP, SG) by swapping the location lookup file.

---

## Network Topology

5G mobile carrier WDM backbone ring — **Central Victoria, Australia** scenario.

**Router → Location mapping** (stored in `lookups/au_router_areas.csv`):

| Router | Model | Location |
|--------|-------|----------|
| R2-NCS5504 | NCS 5504 | Melbourne |
| R3-NCS5504 | NCS 5504 | Geelong |
| R4-NCS55A2 | NCS 55A2 | Warragul |
| R5-NCS55A2 | NCS 55A2 | Ballarat |
| R6-NCS560 | NCS 560 | Traralgon |
| R7-NCS560 | NCS 560 | Bendigo |
| R8-NCS540 | NCS 540 | Wodonga |
| R9-NCS540 | NCS 540 | Shepparton |

Japanese version: `lookups/jp_router_areas.csv` (maps same routers to cities in western Japan).

---

## VLAN Paths (CNC Aggregation)

| VLAN | Path |
|------|------|
| VLAN 1001 | R9 → R8 → R6 → R4 → R2 (Shepparton→Wodonga→Traralgon→Warragul→Melbourne) |
| VLAN 1002 | R9 → R7 → R5 → R3 → R2 (Shepparton→Bendigo→Ballarat→Geelong→Melbourne) |
| VLAN 1003 | R9 → R7 → R5 → R3 → R2 (same physical path as 1002) |
| VLAN 1004 | (similar pattern — details TBD) |

Routing uses **SR-TE (Segment Routing - Traffic Engineering)**, not ECMP. Path changes dynamically based on slice state (`cnc_srte_path_json` field). VLAN 1002/1003 share the same physical R5-R7 link.

---

## Data Sources

| Source | Coverage | Key Metrics |
|--------|----------|-------------|
| ThousandEyes | End-to-end (UE→Internet) | response_time_ms, throughput_kbps, network_latency_ms, network_loss_pct |
| TWAMP | R2 ↔ R9 per VLAN | rt_dp50, rt_dp95 (latency), rt_jp95 (jitter), dl_lostperc, ul_lostperc |
| eNB/gNB | RAN | Connected UEs, throughput |
| FWA/ONU | RAN/Access | Signal strength, data volume |
| Syslog | Device-level | Interface events, hardware errors |
| Telemetry | Per-interface | Latency, jitter, packet loss |
| cnc_srte_path_json | CNC routers | Active SR-TE path per VLAN |

**TE test setup:** Agent behind R9 runs HTTP test to google.com every 1 minute.
**TE sourcetypes used:** `cisco:thousandeyes:metric`, `cisco:thousandeyes:alerts` (path-vis excluded — CNC routers don't respond to ICMP).
**TWAMP agents:** Only on R2 and R9 (budget constraint — not on intermediate routers).

---

## Real Lab Data Observations

Data collected from Cisco internal lab (synthetic traffic, not production):
- **VLAN 1001/1004 rt_dp50:** consistently ~50ms round-trip
- **VLAN 1002/1003 rt_dp50:** mostly ~100-102ms, with occasional drops to 50-51ms (SR-TE reroute events)
- Upload/download jitter (ul_lostperc, dl_lostperc): very low in normal operation

**Note:** Lab uses a small-scale network (not a real carrier-scale WDM). Latency values reflect lab topology, not real production. For the workshop, use insight-based realistic values (50-80ms for network latency) rather than copying lab values directly.
