# cisco:thousandeyes:metric

HTTP test metrics from a ThousandEyes Cloud & Enterprise Agent behind R9-NCS540 (Shepparton) to google.com, running every minute.

## Placeholder Convention

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{timestamp}}` | Region-local wall time for the test run (same as workshop `region` in `ai_lab_scenarios`) | `2026-04-21T10:00:00` |
| `{{sequence}}` | Incrementing integer, unique per event | `1001` |
| `{{response_time_ms}}` | HTTP response time in seconds (float) | `0.187` |
| `{{throughput_kbps}}` | HTTP throughput in kbps (float) | `2345.6` |
| `{{availability}}` | Availability percentage (0 or 100) | `100` |
| `{{network_latency_ms}}` | Network latency in milliseconds (float) | `12.4` |
| `{{network_jitter_ms}}` | Network jitter in milliseconds (float) | `1.2` |
| `{{network_loss_pct}}` | Packet loss percentage (float) | `0.0` |
| `{{http_status_code}}` | HTTP response status code | `200` |

## Notes

- `thousandeyes.source.agent.name` is always `R9-NCS540` for this scenario
- `thousandeyes.test.name` is `R9-to-Google-HTTP`
- `thousandeyes.test.type` is `http-server`
- `server.address` is always `google.com`
- The `timestamp` key is present in the JSON; `backfill_log.py` fills it from the same local datetime as the other metric placeholders. `default/props.conf` for `cisco:thousandeyes:metric` uses `TIME_PREFIX` / `TIME_FORMAT` so `_time` matches that value.
