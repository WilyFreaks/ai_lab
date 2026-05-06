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

TWAMP/PCA interpretation note:

- In this workshop model, TWAMP CSV packet-rate style fields from PCA telemetry are treated as packets per second (pps).
- Record generation cadence (for example 1 minute or 10 seconds) is the sampling/report interval and does not redefine the rate unit itself.

## Splunk storage model (workshop)

Indexes are defined in `default/indexes.conf`. Current intent:

- **Raw/ingest indexes** (populated from workshop generators and monitor inputs)
  - `thousandeyes`, `twamp`, `ran`, `fwa`, `syslog`, `telemetry`, `ios`
  - Current implementation status:
    - active generator/monitor wiring: `thousandeyes`, `telemetry`
    - planned next direct-ingest streams: `twamp`, `syslog`, `ios`
    - reserved for other scenarios: `ran`, `fwa`
- **Derived `alerts` index**
  - `alerts` is reserved for *scheduled-search output* (workshop “alerting” signals).
  - It is expected to be empty until those scheduled searches run, and it does not require `samples/...` templates.
- **Derived `episode` index**
  - `episode` is reserved for a higher-level rollup of `alerts` (for example “episodes” as aggregated windows).
  - The materialization schedule and SPL will be defined later (not shipped in `default/` yet).
  - Like `alerts`, it is not expected to have a `samples/...` file-ingest path.

**Naming note:** “CNC” still appears in field names, sourcetypes, and paths (for example `cnc_interface_counter_json` and `cnc_srte_path_json`) because that is the domain data model, but the old duplicate Splunk index named `cnc` is intentionally removed in favor of `telemetry` for interface telemetry and `alerts` for scheduled alert outputs.

---

## Real Lab Data Observations

Data collected from Cisco internal lab (synthetic traffic, not production):
- **VLAN 1001/1004 rt_dp50:** consistently ~50ms round-trip
- **VLAN 1002/1003 rt_dp50:** mostly ~100-102ms, with occasional drops to 50-51ms (SR-TE reroute events)
- Upload/download jitter (ul_lostperc, dl_lostperc): very low in normal operation

**Note:** Lab uses a small-scale network (not a real carrier-scale WDM). Latency values reflect lab topology, not real production. For the workshop, use insight-based realistic values (50-80ms for network latency) rather than copying lab values directly.

---

## Operational Guardrails

Key project behavior that must remain stable across changes:

- Runtime mutable state is written to `local/ai_lab_scenarios.conf` (not `default/` files).
- Workshop generation is host-gated via region selection and baseline enablement before launch.
- Historical and live generation must preserve timeline continuity across Splunk restarts.
- Canonical verification entrypoint: `bash scripts/test_smoke.sh` (4-check smoke: Python syntax, runtime preconditions, spool empty, app indexes empty).
- Environment reset for repeatable workshops/tests is handled by:
  - `scripts/reset_workshop_state.sh`

### Handoff: operators and the next implementer

#### Resume after a break (minimal context)

Use this when you are tired or returning cold — **one read, then pause**.

1. **Where you left off (optional narrative):** if you use the project journal, open `docs/daily_activity_timeline.md` and find the latest **Resume anchor**. The AI session rule is: read that file first when you ask “where am I” in chat. The journal is updated **only when you explicitly request** a timeline update.
2. **Authoritative behavior:** `docs/project_script_design.md`, `docs/project_conf_design.md`, `docs/project_scenario_*.md`, and per-stream `samples/.../README.md` — not stale chat.
3. **Packaging vs runtime:** ship scenario defaults and docs in **`default/`**; Splunk/workshop **runtime** mutates **`local/ai_lab_scenarios.conf`**. Do not ask tooling to pre-fill **`local/`** for routine changes.
4. **After any full workshop reset:** run `bash scripts/test_smoke.sh` immediately; do not run baseline/data-quality scripts until the region is locked and generators have populated indexes.
5. **Live scenario ticks:** `scenario_happening_probability` is read in **`live_log.py`** with **default `1.0` if missing or invalid** — so **`[scenario_1]`** does **not** need `telemetry#cnc_service_health_json#sample.txt#scenario_happening_probability` unless you want a **fractional** (stochastic) skip.
6. **TWAMP panels:** `*_lostperc` on the wire is **integer percent 0–100**; packet-rate style fields are modeled as **pps**; VLAN **1002/1003** loss in **`scenario_1`** should stay aligned with `cnc_interface_counter_json` directional gaps.
7. **After editing `bin/backfill_log.py`, `bin/live_log.py`, or `default/ai_lab_scenarios.conf`:** if **`live_log.py` / `backfill_log.py` are already running**, **restart** those workers (or Splunk) so the new logic and conf merge are picked up.
8. **Verification:** prefer saved searches in app `ai_lab` (list under *Saved-search-first* below); live checks use a recent window (e.g. last 5 minutes).
9. **Scenario control specifics:** `scenario_control.xml` bootstraps `region` via XML `workshopregion action="status"` and links to `/app/ai_lab/scenario_1_$region$`; `scenariocontrol action=set` preserves non-zero `<scenario>_activated` on repeated Enable and sets `0` on Disable.
10. **Scenario 1 telemetry model:** keep immediate `R5->R7` directional gap via `telemetry#cnc_interface_counter_json#sample.json#immediate_gap_*`, and apply slice reroute via `telemetry#cnc_interface_counter_json#sample.json#reroute_*` keys (`from_slice`, `to_slice`, `pct`, `start_minutes`, `ramp_minutes`).
11. **Reroute semantics:** `reroute_pct` is conserved traffic shift (remove from impacted slices and redistribute removed volume to healthy slices), not independent `+pct` multiplier on healthy links.
12. **Scenario 1 ThousandEyes timing:** `response_time_ms` supports timed return to baseline through `thousandeyes#cisco:thousandeyes:metric#sample.json#response_time_ms.back_to_baseline_start_minutes` + `...back_to_baseline_ramp_minutes`.
13. **Baseline path magnitudes:** keep reroute chain links (`R8-R6`, `R6-R4`, `R4-R2`) in core-consistent ranges (see `docs/project_conf_design.md`), otherwise reroute effects look artificially small.
14. **Config namespace convention:** use sample-aware keys in `default/ai_lab_scenarios.conf` as `<index>#<sourcetype>#<sample_file>#<param>` (index-first; for example `ios#cisco:ios#sample_bfd.txt#...`). Scenario behavior should be driven by these config entries, not hard-coded scenario constants.

- **Splunk install path:** scripts default to `SPLUNK_HOME=/opt/splunk`. On **macOS** (developer installs), set `SPLUNK_HOME` explicitly, e.g. `export SPLUNK_HOME=/Applications/Splunk`, when running the reset script or any doc examples that call `$SPLUNK_HOME/bin/splunk`.
- **Workshop full reset (destructive):** `bash scripts/reset_workshop_state.sh --yes` — stops Splunk, deletes per-index data under `$SPLUNK_DB`, removes all files under `etc/apps/ai_lab/var/spool/ai_lab` (keeping the directory), removes `local/ai_lab_scenarios.conf`, restarts, then (if set) verifies all `default/indexes.conf` app indexes are empty. **Requires** `SPLUNK_AUTH` (same credentials as the workshop admin user) for the post-start SPL verification. See `docs/project_test_design.md` for the full contract.
- **Workshop full reset (destructive):** `bash scripts/reset_workshop_state.sh --yes` — stops app generators first (`backfill_log.py`/`live_log.py`), confirms no orphan `launcher.py`/`backfill_log.py`/`live_log.py`, stops Splunk, removes all files under `etc/apps/ai_lab/var/spool/ai_lab` (keeping the directory), deletes per-index data under `$SPLUNK_DB`, removes `local/ai_lab_scenarios.conf`, restarts, then verifies all `default/indexes.conf` app indexes are empty. Prefer token auth (`SPLUNK_TOKEN`/`AUTH_TOKEN`) sourced from Cursor MCP config; use `SPLUNK_AUTH` only as fallback. See `docs/project_test_design.md` for the full contract.
- **Mandatory test gate after reset:** always run `bash scripts/test_smoke.sh` immediately after reset and require pass before region-lock/generation tests.
- **Ingestion details** (file monitors, `crcSalt`, spool filename uniqueness, `_time` from JSON): `docs/project_conf_design.md` and the **Ingestion** subsection in `docs/project_script_design.md`. App monitors use **`crcSalt = <SOURCE>`** (literal Splunk token), not a fixed arbitrary string, so the CRC includes each file’s path.
- **Sample contracts:** `samples/<index>/<sourcetype>/README.md` and `sample.<ext>` — keep payload structure aligned with the README/template contract; routing (`index`, `sourcetype`, `host`, `source`) stays in `default/inputs.conf`.
- **SPL style for searches** (review and automation): Cursor skill `~/.cursor/skills-cursor/splunk-search-assistant/SKILL.md`. **App packaging / `inputs.conf` CRC and monitor semantics:** `~/.cursor/skills-cursor/splunk-app-manager/SKILL.md` (includes a short `crcSalt` section).
- **Saved-search-first verification policy:** for app-level checks, prefer saved searches in app `ai_lab` (`telemetry_if_counter_test`, `cnc_interface_ifOutPktsRate_test`, `cnc_interface_ifInPktsRate_test`, `thousandeyes_response_time_sec_test`, `cnc_srte_path_test`, `cnc_service_health_test`, `twamp_event_count_test`, `twamp_dmean_test`, `twamp_jmean_test`). Use a recent window (recommended last 5 minutes) when validating active live generation. Baseline data-quality checks run via `scripts/test_baseline.sh` → `scripts/test_backfill.sh`, which include the TWAMP saved searches above.
- **Scenario dashboard XML:** author in `local/data/ui/views/` (Splunk UI saves here); on explicit sync (“copy local dashboard to default”), full-copy to `default/data/ui/views/` for Git/AMI. At runtime, **`local` overrides `default`** for the same view name—see `docs/project_dashboard_design.md` (*Scenario dashboard authoring*).
- **Credentials for CLI/tests** (workshop): same as below; do not commit real production secrets. Tests expect `SPLUNK_AUTH=admin:password` in the environment.

---

## Local Splunk Credential (Workshop Environment)

- Username: `admin`
- Password: `ailab2025`
