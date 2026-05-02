# cnc_srte_path_json

SR policy path topology snapshots for four VLANs (`cnc_vlan1001`..`cnc_vlan1004`) in the CNC network. The sourcetype is JSON (`cnc_srte_path_json`), while the sample template is stored as `sample.txt` and contains four independent JSON objects (one per VLAN) in a single file.

On generation, the rendered output file for this source is `.txt` (same wire format family as template). Splunk ingest/event breaking then decomposes the payload into individual JSON events.

## Placeholder Convention

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{timestamp}}` | Region-local wall time for the sample (same as workshop `region` in `ai_lab_scenarios`), with a short suffix (`JST` for `jp`, and `AEST`/`AEDT` as applicable for `au` via `Australia/Sydney`) | `2026-04-21T10:00:00 JST` |
| `{{impacted_vlan_path}}` | JSON array elements for the impacted SR path in VLAN1002/VLAN1003. This is inserted directly inside the `hops` array and therefore must be JSON-compatible array item text (not a quoted placeholder string). | `"R9-NCS540", "R7-NCS560", "R5-NCS55A2", "R3-NCS5504", "R2-NCS5504"` |

## Topology Intent in This Sample

- `cnc_vlan1001` and `cnc_vlan1004` are baseline path references in the sample.
- `cnc_vlan1002` and `cnc_vlan1003` are scenario-impacted VLANs and use `{{impacted_vlan_path}}`.
- Scenario profile for impacted VLANs can shorten path to endpoint-only form (for example `"R2-NCS5504"`).

## Scenario Keys (`ai_lab_scenarios.conf`)

- `telemetry#cnc_srte_path_json#interval`
  - Emit cadence in minutes for this sourcetype.
- `telemetry#cnc_srte_path_json#scenario_happening_probability`
  - Probability range `0..1`, clamped by generator logic.
  - `0` means scenario variant never happens.
  - `1` means scenario variant always happens.
  - Active scenario sections can override this baseline key during fault windows.

## Notes

- Template file extension is intentionally `.txt`; loader logic must detect extension first and apply the matching parse path.
- `.txt` sample extension means `.txt` spool output for this source; payload content in this sample is JSON-shaped and ingested as `sourcetype=cnc_srte_path_json`.
- Do not add keys or alter structure in `sample.txt` unless this README and `default/ai_lab_scenarios.conf` are updated together.
- Splunk routing metadata (`index`, `sourcetype`, `source`, `host`) belongs in `default/inputs.conf` monitor stanzas, not inside payload fields unless explicitly required.
