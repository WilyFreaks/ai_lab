# pca_twamp_csv

TWAMP synthetic metrics for slice sessions (CSV format). The sourcetype is `pca_twamp_csv` and the sample template is `sample.csv`.

## Placeholder Convention

`sample.csv` line 1 (header) is the source of truth. **Generators write this header only once per spool file**; each subsequent event appends rendered data rows (lines 2–5 of the template) without repeating the header.

For fields starting with `ul_`, `dl_`, and `rt_`, placeholders must use:

- `{{<<SLICE>>_<<HEADER_FIELD>>}}`
- Example: `{{slice1001_ul_firstpktSeq}}`

### Header-derived placeholders (`ul_*`, `dl_*`, `rt_*`)

Example convention (Slice 1001): `{{slice1001_<field_name>}}`

UL placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{slice1001_ul_statStatus}}` | Uplink one-way (source to destination) measurement status code | `1792` |
| `{{slice1001_ul_firstpktSeq}}` | Uplink one-way (source to destination) first packet sequence number in window | `649489150` |
| `{{slice1001_ul_lastpktSeq}}` | Uplink one-way (source to destination) last packet sequence number in window | `649490074` |
| `{{slice1001_ul_rxpkts}}` | Uplink one-way (source to destination) received packet count in window | `925` |
| `{{slice1001_ul_rxbytes}}` | Uplink one-way (source to destination) received byte count in window | `505050` |
| `{{slice1001_ul_misorderpkts}}` | Uplink one-way (source to destination) out-of-order packet count | `0` |
| `{{slice1001_ul_duplicatepkts}}` | Uplink one-way (source to destination) duplicate packet count | `0` |
| `{{slice1001_ul_toolatepkts}}` | Uplink one-way (source to destination) late packet count (outside acceptance window) | `0` |
| `{{slice1001_ul_lostpkts}}` | Uplink one-way (source to destination) lost packet count | `0` |
| `{{slice1001_ul_lostperiods}}` | Uplink one-way (source to destination) count of loss periods | `0` |
| `{{slice1001_ul_lostburstmin}}` | Uplink one-way (source to destination) minimum burst length of consecutive lost packets | `0` |
| `{{slice1001_ul_lostburstmax}}` | Uplink one-way (source to destination) maximum burst length of consecutive lost packets | `0` |
| `{{slice1001_ul_lostperc}}` | Uplink one-way packet loss (**integer percent 0–100**; generators set from `*_rxpkts_expected`, `*_rxpkts_drop_rate`, and derived `*_rxpkts`) | `0` |
| `{{slice1001_ul_mos}}` | Uplink one-way (source to destination) Mean Opinion Score (MOS) quality estimate | `4409286` |
| `{{slice1001_ul_r}}` | Uplink one-way (source to destination) R-factor quality score | `93200000` |
| `{{slice1001_ul_tosmin}}` | Uplink one-way (source to destination) minimum observed IP ToS/DSCP value | `0` |
| `{{slice1001_ul_tosmax}}` | Uplink one-way (source to destination) maximum observed IP ToS/DSCP value | `0` |
| `{{slice1001_ul_vpriomin}}` | Uplink one-way (source to destination) minimum observed VLAN priority (802.1p) | `0` |
| `{{slice1001_ul_vpriomax}}` | Uplink one-way (source to destination) maximum observed VLAN priority (802.1p) | `0` |
| `{{slice1001_ul_cksum}}` | Uplink one-way (source to destination) checksum/error indicator from exporter | `0` |
| `{{slice1001_ul_ttlmin}}` | Uplink one-way (source to destination) minimum observed IP TTL | `250` |
| `{{slice1001_ul_ttlmax}}` | Uplink one-way (source to destination) maximum observed IP TTL | `250` |
| `{{slice1001_ul_dmin}}` | Uplink one-way (source to destination) minimum delay | `22` |
| `{{slice1001_ul_dp25}}` | Uplink one-way (source to destination) p25 delay | `26` |
| `{{slice1001_ul_dp50}}` | Uplink one-way (source to destination) p50 delay | `28` |
| `{{slice1001_ul_dp75}}` | Uplink one-way (source to destination) p75 delay | `30` |
| `{{slice1001_ul_dp95}}` | Uplink one-way (source to destination) p95 delay | `33` |
| `{{slice1001_ul_dpLo}}` | Uplink one-way (source to destination) low-segment delay distribution marker | `33` |
| `{{slice1001_ul_dpMi}}` | Uplink one-way (source to destination) mid-segment delay distribution marker | `34` |
| `{{slice1001_ul_dpHi}}` | Uplink one-way (source to destination) high-segment delay distribution marker | `35` |
| `{{slice1001_ul_dmax}}` | Uplink one-way (source to destination) maximum delay | `38` |
| `{{slice1001_ul_dmean}}` | Uplink one-way (source to destination) mean delay | `28` |
| `{{slice1001_ul_dStdDev}}` | Uplink one-way (source to destination) delay standard deviation | `2` |
| `{{slice1001_ul_jmin}}` | Uplink one-way (source to destination) minimum jitter | `0` |
| `{{slice1001_ul_jp25}}` | Uplink one-way (source to destination) p25 jitter | `1` |
| `{{slice1001_ul_jp50}}` | Uplink one-way (source to destination) p50 jitter | `2` |
| `{{slice1001_ul_jp75}}` | Uplink one-way (source to destination) p75 jitter | `4` |
| `{{slice1001_ul_jp95}}` | Uplink one-way (source to destination) p95 jitter | `7` |
| `{{slice1001_ul_jpLo}}` | Uplink one-way (source to destination) low-segment jitter distribution marker | `7` |
| `{{slice1001_ul_jpMi}}` | Uplink one-way (source to destination) mid-segment jitter distribution marker | `9` |
| `{{slice1001_ul_jpHi}}` | Uplink one-way (source to destination) high-segment jitter distribution marker | `9` |
| `{{slice1001_ul_jmax}}` | Uplink one-way (source to destination) maximum jitter | `12` |
| `{{slice1001_ul_jmean}}` | Uplink one-way (source to destination) mean jitter | `2` |
| `{{slice1001_ul_jStdDev}}` | Uplink one-way (source to destination) jitter standard deviation | `2` |
| `{{slice1001_ul_dvp25}}` | Uplink one-way (source to destination) p25 delay variation | `4` |
| `{{slice1001_ul_dvp50}}` | Uplink one-way (source to destination) p50 delay variation | `6` |
| `{{slice1001_ul_dvp75}}` | Uplink one-way (source to destination) p75 delay variation | `8` |
| `{{slice1001_ul_dvp95}}` | Uplink one-way (source to destination) p95 delay variation | `11` |
| `{{slice1001_ul_dvpLo}}` | Uplink one-way (source to destination) low-segment delay-variation distribution marker | `11` |
| `{{slice1001_ul_dvpMi}}` | Uplink one-way (source to destination) mid-segment delay-variation distribution marker | `12` |
| `{{slice1001_ul_dvpHi}}` | Uplink one-way (source to destination) high-segment delay-variation distribution marker | `13` |
| `{{slice1001_ul_dvmax}}` | Uplink one-way (source to destination) maximum delay variation | `16` |
| `{{slice1001_ul_dvmean}}` | Uplink one-way (source to destination) mean delay variation | `6` |

DL placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{slice1001_dl_statStatus}}` | Downlink one-way (destination to source) measurement status code | `1792` |
| `{{slice1001_dl_firstpktSeq}}` | Downlink one-way (destination to source) first packet sequence number in window | `372856579` |
| `{{slice1001_dl_lastpktSeq}}` | Downlink one-way (destination to source) last packet sequence number in window | `372857503` |
| `{{slice1001_dl_rxpkts}}` | Downlink one-way (destination to source) received packet count in window | `925` |
| `{{slice1001_dl_rxbytes}}` | Downlink one-way (destination to source) received byte count in window | `505050` |
| `{{slice1001_dl_misorderpkts}}` | Downlink one-way (destination to source) out-of-order packet count | `0` |
| `{{slice1001_dl_duplicatepkts}}` | Downlink one-way (destination to source) duplicate packet count | `0` |
| `{{slice1001_dl_toolatepkts}}` | Downlink one-way (destination to source) late packet count (outside acceptance window) | `0` |
| `{{slice1001_dl_lostpkts}}` | Downlink one-way (destination to source) lost packet count | `0` |
| `{{slice1001_dl_lostperiods}}` | Downlink one-way (destination to source) count of loss periods | `0` |
| `{{slice1001_dl_lostburstmin}}` | Downlink one-way (destination to source) minimum burst length of consecutive lost packets | `0` |
| `{{slice1001_dl_lostburstmax}}` | Downlink one-way (destination to source) maximum burst length of consecutive lost packets | `0` |
| `{{slice1001_dl_lostperc}}` | Downlink one-way packet loss (**integer percent 0–100**; same derivation as UL) | `0` |
| `{{slice1001_dl_mos}}` | Downlink one-way (destination to source) Mean Opinion Score (MOS) quality estimate | `4409286` |
| `{{slice1001_dl_r}}` | Downlink one-way (destination to source) R-factor quality score | `93200000` |
| `{{slice1001_dl_tosmin}}` | Downlink one-way (destination to source) minimum observed IP ToS/DSCP value | `0` |
| `{{slice1001_dl_tosmax}}` | Downlink one-way (destination to source) maximum observed IP ToS/DSCP value | `0` |
| `{{slice1001_dl_vpriomin}}` | Downlink one-way (destination to source) minimum observed VLAN priority (802.1p) | `0` |
| `{{slice1001_dl_vpriomax}}` | Downlink one-way (destination to source) maximum observed VLAN priority (802.1p) | `0` |
| `{{slice1001_dl_cksum}}` | Downlink one-way (destination to source) checksum/error indicator from exporter | `0` |
| `{{slice1001_dl_ttlmin}}` | Downlink one-way (destination to source) minimum observed IP TTL | `250` |
| `{{slice1001_dl_ttlmax}}` | Downlink one-way (destination to source) maximum observed IP TTL | `250` |
| `{{slice1001_dl_dmin}}` | Downlink one-way (destination to source) minimum delay | `22` |
| `{{slice1001_dl_dp25}}` | Downlink one-way (destination to source) p25 delay | `22` |
| `{{slice1001_dl_dp50}}` | Downlink one-way (destination to source) p50 delay | `23` |
| `{{slice1001_dl_dp75}}` | Downlink one-way (destination to source) p75 delay | `23` |
| `{{slice1001_dl_dp95}}` | Downlink one-way (destination to source) p95 delay | `24` |
| `{{slice1001_dl_dpLo}}` | Downlink one-way (destination to source) low-segment delay distribution marker | `24` |
| `{{slice1001_dl_dpMi}}` | Downlink one-way (destination to source) mid-segment delay distribution marker | `24` |
| `{{slice1001_dl_dpHi}}` | Downlink one-way (destination to source) high-segment delay distribution marker | `24` |
| `{{slice1001_dl_dmax}}` | Downlink one-way (destination to source) maximum delay | `25` |
| `{{slice1001_dl_dmean}}` | Downlink one-way (destination to source) mean delay | `22` |
| `{{slice1001_dl_dStdDev}}` | Downlink one-way (destination to source) delay standard deviation | `0` |
| `{{slice1001_dl_jmin}}` | Downlink one-way (destination to source) minimum jitter | `0` |
| `{{slice1001_dl_jp25}}` | Downlink one-way (destination to source) p25 jitter | `0` |
| `{{slice1001_dl_jp50}}` | Downlink one-way (destination to source) p50 jitter | `1` |
| `{{slice1001_dl_jp75}}` | Downlink one-way (destination to source) p75 jitter | `1` |
| `{{slice1001_dl_jp95}}` | Downlink one-way (destination to source) p95 jitter | `2` |
| `{{slice1001_dl_jpLo}}` | Downlink one-way (destination to source) low-segment jitter distribution marker | `2` |
| `{{slice1001_dl_jpMi}}` | Downlink one-way (destination to source) mid-segment jitter distribution marker | `2` |
| `{{slice1001_dl_jpHi}}` | Downlink one-way (destination to source) high-segment jitter distribution marker | `2` |
| `{{slice1001_dl_jmax}}` | Downlink one-way (destination to source) maximum jitter | `3` |
| `{{slice1001_dl_jmean}}` | Downlink one-way (destination to source) mean jitter | `0` |
| `{{slice1001_dl_jStdDev}}` | Downlink one-way (destination to source) jitter standard deviation | `0` |
| `{{slice1001_dl_dvp25}}` | Downlink one-way (destination to source) p25 delay variation | `0` |
| `{{slice1001_dl_dvp50}}` | Downlink one-way (destination to source) p50 delay variation | `1` |
| `{{slice1001_dl_dvp75}}` | Downlink one-way (destination to source) p75 delay variation | `1` |
| `{{slice1001_dl_dvp95}}` | Downlink one-way (destination to source) p95 delay variation | `2` |
| `{{slice1001_dl_dvpLo}}` | Downlink one-way (destination to source) low-segment delay-variation distribution marker | `2` |
| `{{slice1001_dl_dvpMi}}` | Downlink one-way (destination to source) mid-segment delay-variation distribution marker | `2` |
| `{{slice1001_dl_dvpHi}}` | Downlink one-way (destination to source) high-segment delay-variation distribution marker | `2` |
| `{{slice1001_dl_dvmax}}` | Downlink one-way (destination to source) maximum delay variation | `3` |
| `{{slice1001_dl_dvmean}}` | Downlink one-way (destination to source) mean delay variation | `0` |

RT placeholders:

| Placeholder | Description | Example |
|-------------|-------------|---------|
| `{{slice1001_rt_statStatus}}` | Round-trip measurement status code | `1536` |
| `{{slice1001_rt_firstpktSeq}}` | Round-trip first packet sequence number in window | `649489150` |
| `{{slice1001_rt_lastpktSeq}}` | Round-trip last packet sequence number in window | `649490074` |
| `{{slice1001_rt_rxpkts}}` | Round-trip received packet count in window | `925` |
| `{{slice1001_rt_rxbytes}}` | Round-trip received byte count in window | `505050` |
| `{{slice1001_rt_dmin}}` | Round-trip minimum delay | `45` |
| `{{slice1001_rt_dp25}}` | Round-trip p25 delay | `49` |
| `{{slice1001_rt_dp50}}` | Round-trip p50 delay | `51` |
| `{{slice1001_rt_dp75}}` | Round-trip p75 delay | `53` |
| `{{slice1001_rt_dp95}}` | Round-trip p95 delay | `56` |
| `{{slice1001_rt_dpLo}}` | Round-trip low-segment delay distribution marker | `57` |
| `{{slice1001_rt_dpMi}}` | Round-trip mid-segment delay distribution marker | `58` |
| `{{slice1001_rt_dpHi}}` | Round-trip high-segment delay distribution marker | `58` |
| `{{slice1001_rt_dmax}}` | Round-trip maximum delay | `61` |
| `{{slice1001_rt_dmean}}` | Round-trip mean delay | `51` |
| `{{slice1001_rt_dStdDev}}` | Round-trip delay standard deviation | `2` |
| `{{slice1001_rt_jmin}}` | Round-trip minimum jitter | `0` |
| `{{slice1001_rt_jp25}}` | Round-trip p25 jitter | `1` |
| `{{slice1001_rt_jp50}}` | Round-trip p50 jitter | `2` |
| `{{slice1001_rt_jp75}}` | Round-trip p75 jitter | `4` |
| `{{slice1001_rt_jp95}}` | Round-trip p95 jitter | `7` |
| `{{slice1001_rt_jpLo}}` | Round-trip low-segment jitter distribution marker | `8` |
| `{{slice1001_rt_jpMi}}` | Round-trip mid-segment jitter distribution marker | `9` |
| `{{slice1001_rt_jpHi}}` | Round-trip high-segment jitter distribution marker | `10` |
| `{{slice1001_rt_jmax}}` | Round-trip maximum jitter | `12` |
| `{{slice1001_rt_jmean}}` | Round-trip mean jitter | `2` |
| `{{slice1001_rt_jStdDev}}` | Round-trip jitter standard deviation | `2` |
| `{{slice1001_rt_dvp25}}` | Round-trip p25 delay variation | `4` |
| `{{slice1001_rt_dvp50}}` | Round-trip p50 delay variation | `6` |
| `{{slice1001_rt_dvp75}}` | Round-trip p75 delay variation | `8` |
| `{{slice1001_rt_dvp95}}` | Round-trip p95 delay variation | `11` |
| `{{slice1001_rt_dvpLo}}` | Round-trip low-segment delay-variation distribution marker | `12` |
| `{{slice1001_rt_dvpMi}}` | Round-trip mid-segment delay-variation distribution marker | `13` |
| `{{slice1001_rt_dvpHi}}` | Round-trip high-segment delay-variation distribution marker | `13` |
| `{{slice1001_rt_dvmax}}` | Round-trip maximum delay variation | `16` |
| `{{slice1001_rt_dvmean}}` | Round-trip mean delay variation | `6` |

## CSV numeric typing (wire format)

Real PCA TWAMP CSV exports use **integer cells only** (no fractional literals). After `metric_value` (including `noise_stdev` on delay/jitter metrics), generators round to integers for every `slice####_*` field: `int(round(value))` in `format_pca_twamp_csv_metric` in `bin/live_log.py` and `bin/backfill_log.py`. For each emitted event, delay/jitter noise uses **one** standard-normal draw **per slice** (`noise_stdev * ε`) so all percentiles for that slice move together—this keeps `dmin ≤ dp25 ≤ …` plausible while still letting integers **±1** (or more) across ticks when `default.noise_stdev` is in roughly the **0.35–0.55** range.

Packet sequence contract per slice (applies to `ul_*`, `dl_*`, and `rt_*`):

- Initial baseline seed: first generated `<dir>_firstpktSeq` starts at `5000000`.
- `<dir>_rxpkts_expected` is generated first (per template/conf parameter model).
- `<dir>_rxpkts_drop_rate` is a ratio in `[0,1]`.
- `<dir>_rxpkts = <dir>_rxpkts_expected * (1 - <dir>_rxpkts_drop_rate)`.
- `<dir>_rxbytes = <dir>_rxpkts * 546` (effective payload size per packet for this workshop model; **generators compute this**—do not rely on separate `*_rxbytes` keys in `ai_lab_scenarios.conf` unless you add them as explicit placeholders).
- `<dir>_lastpktSeq = <dir>_firstpktSeq + <dir>_rxpkts_expected` (use expected count, not `<dir>_rxpkts`, to model packet drop).
- `<dir>_lostpkts` and `<dir>_lostperc` are recomputed from expected, drop rate, and derived `<dir>_rxpkts` (generators overwrite template/conf placeholders for these).
- `<dir>_lostperc` on the wire is an **integer percent 0–100** (`round(100 * lost / expected)`), aligned with workshop dashboards that chart loss on a 0–100% axis.
- Continuity expectation: next event `<dir>_firstpktSeq = previous <dir>_lastpktSeq + 1`.

**Conf vs `sample.csv`:** The shipped template lists `{{slice1001_ul_rxpkts}}` (and DL/RT) but not `{{slice1001_ul_rxpkts_expected}}`. Expected counts and drop rates are defined only under keys like `twamp#pca_twamp_csv#slice1001_ul_rxpkts_expected`; `backfill_log.py` / `live_log.py` **read those keys inside `apply_twamp_ul_packet_sequence`** and then overwrite `*_rxpkts` / `*_rxbytes` per the formulas above.

## Delay and jitter variation (workshop tuning)

Per-metric keys in `default/ai_lab_scenarios.conf` use the same `metric_value` pipeline as other sources (see `docs/project_conf_design.md`):

1. **Per-event “wobble” without hourly curves:** set `noise_stdev` on the TWAMP keys you want to jitter (for example `twamp#pca_twamp_csv#slice1001_ul_dp50.noise_stdev = 0.15`). Each emitted row gets `value += random.gauss(0, noise_stdev)` after the base / `daily_min`–`daily_max` step.
2. **Time-of-day shape:** add `peak_rate_00` … `peak_rate_23` for that metric prefix. When `daily_min`, `daily_max`, and the current hour’s `peak_rate_*` are all present, the value follows the interpolated daily curve (and still gets `noise_stdev` if set).
3. **Ordering:** Real PCA rows keep an ordering such as `dmin ≤ dp25 ≤ dp50 ≤ … ≤ dmax`. Generators apply **shared ε per slice** for delay/jitter noise (see above). If per-metric `.noise_stdev` overrides differ a lot, rare inversions are still possible—keep overrides near `default.noise_stdev` if that matters.

## Splunk generation cadence vs PCA row window

These are intentionally different layers:

1. **When the workshop generator writes a new CSV row (Splunk ingest cadence)**  
   Controlled by `[baseline]` **`<<index>>#<<sourcetype>>#interval`**, in **minutes**:
   - **`live_log.py`:** on each 1-minute scheduler tick, that source is eligible when `minute_of_hour % interval == 0`.
   - **`backfill_log.py`:** scans the full backfill window in **one run** and emits spool output per source; timestamps advance by **`interval * 60`** seconds between events **unless** `event_interval_sec` is set (see below).  
   With **`interval = 1`** and **no** `event_interval_sec`, live emits **one** event per eligible minute. With **`interval = 15`**, live emits on minutes `0, 15, 30, 45`.

2. **Sub-minute events:** `[baseline]` **`<<index>>#<<sourcetype>>#event_interval_sec`** (optional, **seconds**)
   - If **absent or invalid:** one event per eligible **`interval`** minute (live), and backfill advances by **`interval * 60`** seconds per event.
   - If **set (positive):**
     - **`live_log.py`:** on each eligible tick, emits **multiple** events: timestamps end at the tick second, spaced by **`event_interval_sec`**, with **N = max(1, (interval×60) // event_interval_sec)** samples in that window (so e.g. `interval=1`, `event_interval_sec=10` → 6 events per minute when the source is due).
     - **`backfill_log.py`:** advances synthetic time by **`event_interval_sec`** seconds between events across the whole backfill span (same run still writes **one** spool file per stream with **many** lines).

3. **What a single CSV row represents (PCA export / measurement window)**  
   - Header **`Interval`** (see `sample.csv`): exporter interval in **seconds** (the shipped template uses **`10`** — a 10 s window in that column).  
   - **`{{intervalms}}`:** resolved from **`twamp#pca_twamp_csv#intervalms`** in `default/ai_lab_scenarios.conf` / effective `[baseline]` (milliseconds). For a 10 s window use **`10000`**, consistent with **`Interval * 1000`**.  
   Keep **`Interval`**, **`intervalms`**, and the **`Packet Rate` × window** math on the same window so counts stay coherent.

4. **Relating pps to `*_rxpkts_expected`**  
   With **`Packet Rate` = packets per second (pps)**, the notional expected received count for a row matches **`Packet Rate * window_seconds`**, where **`window_seconds`** is the modeled window (typically **`Interval`**, or **`intervalms / 1000`**). The generator then applies **`*_rxpkts_drop_rate`** to derive **`*_rxpkts`** (see packet sequence contract above). Example: 10 s window → **`Packet Rate * 10`** at zero drop.

## Notes

- Template extension is `.csv`; generator output for this source should stay `.csv`.
- Keep routing metadata (`index`, `sourcetype`, `source`, `host`) in `default/inputs.conf`, not inside payload.
- If placeholders change in `sample.csv`, update `default/ai_lab_scenarios.conf` keys and this README together.
- Assumption for this workshop dataset: `Packet Rate` is interpreted as packets per second (pps) from PCA-collected Cisco telemetry.
- Under this assumption, expected packet count in one record window is `Packet Rate * window_seconds` (for example, 1-minute window -> `Packet Rate * 60`; 10-second window -> `Packet Rate * 10`).
