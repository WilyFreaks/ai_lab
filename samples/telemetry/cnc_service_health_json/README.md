# cnc_service_health_json

Service-health snapshot payload for CNC VPN slices. The sourcetype is JSON (`cnc_service_health_json`) and the sample template is `sample.txt`.

## Placeholder convention

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{timestamp}}` | Region-local wall time for the sample (same workshop `region`), with short suffix (`JST` for `jp`, and `AEST`/`AEDT` for `au`) | `2026-04-21T10:00:00 JST` |
| `{{impacted_sre_policy_health_status}}` | Scenario-controlled health status used in impacted VLAN `sr_policy` rows (VLAN1002/VLAN1003). Baseline uses `SERVICE_UP`; scenario can override to `SERVICE_DEGRADED`. | `SERVICE_UP` |
| `{{impacted_sr_policy_health_score}}` | Integer `health_score` on the same **sr_policy / R9-NCS540** rows as `impacted_sre_policy_health_status`. Baseline **100**; **`[scenario_1]`** uses **50** when status is degraded. | `100` |

## Conf keys (`default/ai_lab_scenarios.conf`)

- **Baseline** (`[baseline]`): `telemetry#cnc_service_health_json#impacted_sre_policy_health_status`, `telemetry#cnc_service_health_json#impacted_sr_policy_health_score` (typically `SERVICE_UP` / **100**).
- **Scenario 1** (`[scenario_1]`): same keys overridden to **`SERVICE_DEGRADED`** / **50** for impacted **sr_policy** rows (VLAN 1002/1003).
- **`telemetry#cnc_service_health_json#scenario_happening_probability`** (optional): if set to a fraction in **`0..1`**, `live_log.py` may fall back to baseline placeholders for that event; if **omitted** or **invalid**, **`live_log.py`** uses **`1`** (always apply scenario keys during the fault window). **`[scenario_1]`** does not need this key for deterministic degraded rows.

## Payload intent

- `vlan` identifies the VLAN context (for example `cnc_vlan1002`).
- `subservice_health` is an array of per-device health rows.
- Dashboard searches can expand `subservice_health{}` and read:
  - `vpn_name`
  - `category`
  - `device`
  - `health_status`
  - `health_score`
- Placeholders in `sample.txt`: `{{timestamp}}`, `{{impacted_sre_policy_health_status}}`, `{{impacted_sr_policy_health_score}}` (only on VLAN 1002/1003 impacted `sr_policy` rows).

## Notes

- Template file extension is intentionally `.txt`; loader logic should detect extension first and apply the matching parse/render path.
- `.txt` sample extension means `.txt` spool output for this source; payload content in this sample remains JSON-shaped and is ingested as `sourcetype=cnc_service_health_json`.
- Keep routing metadata (`index`, `sourcetype`, `source`, `host`) in `default/inputs.conf`, not inside payload unless explicitly required.
- If you add new placeholders in `sample.txt`, update `default/ai_lab_scenarios.conf` and this README together.
