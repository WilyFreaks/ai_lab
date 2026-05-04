# cnc_interface_counter_json

IOS-XR–style interface counter snapshot: packet rates (`ifInPktsRate` / `ifOutPktsRate`) per interface, nested under `devices → interfaces → … → latest_data`. The workshop topology covers routers **R2–R9** with HundredGig, Bundle-Ether, and FortyGig interfaces as modeled in `sample.json`. One NDJSON object is written per backfill interval (see `default/ai_lab_scenarios.conf` → `telemetry#cnc_interface_counter_json#interval`).

## Placeholder convention

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{timestamp}}` | Region-local wall time for the sample (same as workshop `region` in `ai_lab_scenarios`), with a short suffix (`JST` for `jp`, and `AEST`/`AEDT` as applicable for `au` via `Australia/Sydney`) | `2026-04-21T10:00:00 JST` |
| `{{<name>}}` where `<name>` is `R[2-9]_<interfaceToken>_ifInPktsRate` or `…_ifOutPktsRate` | Float packet rate for that router, interface, and direction. The template name matches the scenario key suffix (see below). | `6.15` |

Interface tokens in placeholder names use underscores instead of `/` (for example `HundredGigE0_0_0_0` for `HundredGigE0/0/0/0`, `Bundle_Ether145` for `Bundle-Ether145`).

## Scenario keys (`ai_lab_scenarios.conf`)

Each metric placeholder has a matching option:

`telemetry#cnc_interface_counter_json#<same_name_as_placeholder>`

Example:

`telemetry#cnc_interface_counter_json#R9_FortyGigE0_0_0_28_ifOutPktsRate = 6`

The same suffix supports optional tuning keys as for other streams (for example `.daily_min`, `.daily_max`, `.peak_rate_HH`, `.weekend_multiplier`, `.noise_stdev`, `.outlier_*`). See `default/ai_lab_scenarios.conf` for the full set.

**Directional pairing (generators):** `telemetry#cnc_interface_counter_json#directional_min_receive_fraction` (default `0.99` in baseline) controls post-render clamping so peer `ifIn` stays within one minus that fraction of the connected `ifOut` (no invented packets). Scenario faults may set it to `0` so large intentional gaps (e.g. scenario 1 on R5→R7) are preserved.

## Metric placeholders in this sample

These are the only `{{…}}` names used in `sample.json` besides `timestamp`:

```
R2_HundredGigE0_0_0_0_ifInPktsRate
R2_HundredGigE0_0_0_0_ifOutPktsRate
R2_HundredGigE0_0_0_2_ifInPktsRate
R2_HundredGigE0_0_0_2_ifOutPktsRate
R3_HundredGigE0_0_0_1_ifInPktsRate
R3_HundredGigE0_0_0_1_ifOutPktsRate
R3_HundredGigE0_0_0_2_ifInPktsRate
R3_HundredGigE0_0_0_2_ifOutPktsRate
R4_Bundle_Ether145_ifInPktsRate
R4_Bundle_Ether145_ifOutPktsRate
R4_HundredGigE0_0_1_0_0_ifInPktsRate
R4_HundredGigE0_0_1_0_0_ifOutPktsRate
R4_HundredGigE0_0_2_0_ifInPktsRate
R4_HundredGigE0_0_2_0_ifOutPktsRate
R4_HundredGigE0_0_2_1_ifInPktsRate
R4_HundredGigE0_0_2_1_ifOutPktsRate
R5_Bundle_Ether145_ifInPktsRate
R5_Bundle_Ether145_ifOutPktsRate
R5_HundredGigE0_0_1_0_0_ifInPktsRate
R5_HundredGigE0_0_1_0_0_ifOutPktsRate
R5_HundredGigE0_0_2_0_ifInPktsRate
R5_HundredGigE0_0_2_0_ifOutPktsRate
R5_HundredGigE0_0_2_1_ifInPktsRate
R5_HundredGigE0_0_2_1_ifOutPktsRate
R6_HundredGigE0_0_0_0_ifInPktsRate
R6_HundredGigE0_0_0_0_ifOutPktsRate
R6_HundredGigE0_0_0_1_ifInPktsRate
R6_HundredGigE0_0_0_1_ifOutPktsRate
R6_HundredGigE0_1_0_0_ifInPktsRate
R6_HundredGigE0_1_0_0_ifOutPktsRate
R7_HundredGigE0_0_0_0_ifInPktsRate
R7_HundredGigE0_0_0_0_ifOutPktsRate
R7_HundredGigE0_0_0_1_ifInPktsRate
R7_HundredGigE0_0_0_1_ifOutPktsRate
R7_HundredGigE0_1_0_0_ifInPktsRate
R7_HundredGigE0_1_0_0_ifOutPktsRate
R8_FortyGigE0_0_0_28_ifInPktsRate
R8_FortyGigE0_0_0_28_ifOutPktsRate
R8_FortyGigE0_0_1_1_ifInPktsRate
R8_FortyGigE0_0_1_1_ifOutPktsRate
R8_HundredGigE0_0_1_0_ifInPktsRate
R8_HundredGigE0_0_1_0_ifOutPktsRate
R9_FortyGigE0_0_0_28_ifInPktsRate
R9_FortyGigE0_0_0_28_ifOutPktsRate
R9_HundredGigE0_0_0_29_ifInPktsRate
R9_HundredGigE0_0_0_29_ifOutPktsRate
```

## Notes

- Do not add JSON keys, devices, or interfaces that are not in `sample.json` unless this README and `default/ai_lab_scenarios.conf` are updated to match. Splunk routing metadata belongs in `default/inputs.conf` (not embedded in the JSON).
- Ingest: `index=telemetry`, `sourcetype=cnc_interface_counter_json`, `host=router_int_count`, `source=ai_lab:backfill:telemetry` (see `default/inputs.conf`).
- `backfill_log.py` fills `{{timestamp}}` the same way as the ThousandEyes metric template. Nested `latest_data.timestamp` values follow that string.
- Timestamp extraction for this sourcetype is configured under `[cnc_interface_counter_json]` in `default/props.conf` (`TIME_PREFIX` / `TIME_FORMAT` with the timezone token, plus indexed JSON settings).
