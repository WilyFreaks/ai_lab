# cnc_service_health_json

Service-health snapshot payload for CNC VPN slices. The sourcetype is JSON (`cnc_service_health_json`) and the sample template is `sample.txt`.

## Placeholder convention

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{timestamp}}` | Region-local wall time for the sample (same workshop `region`), with short suffix (`JST` for `jp`, and `AEST`/`AEDT` for `au`) | `2026-04-21T10:00:00 JST` |
| `{{impacted_sre_policy_health_status}}` | Scenario-controlled health status used in impacted VLAN `sr_policy` rows (VLAN1002/VLAN1003). Baseline uses `SERVICE_UP`; scenario can override to `SERVICE_DEGRADED`. | `SERVICE_UP` |

## Payload intent

- `vlan` identifies the VLAN context (for example `cnc_vlan1002`).
- `subservice_health` is an array of per-device health rows.
- Dashboard searches can expand `subservice_health{}` and read:
  - `vpn_name`
  - `category`
  - `device`
  - `health_status`
  - `health_score`
- Only two placeholders are used in `sample.txt`: `{{timestamp}}` and `{{impacted_sre_policy_health_status}}`.

## Notes

- Template file extension is intentionally `.txt`; loader logic should detect extension first and apply the matching parse/render path.
- `.txt` sample extension means `.txt` spool output for this source; payload content in this sample remains JSON-shaped and is ingested as `sourcetype=cnc_service_health_json`.
- Keep routing metadata (`index`, `sourcetype`, `source`, `host`) in `default/inputs.conf`, not inside payload unless explicitly required.
- If you add new placeholders in `sample.txt`, update `default/ai_lab_scenarios.conf` and this README together.
