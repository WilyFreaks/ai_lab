# `wdm_pm` sample contract

This directory defines the workshop contract for WDM performance events.

- Index: `syslog`
- Sourcetype: `wdm_pm`
- Template: `sample.csv`

## Purpose

`wdm_pm` provides performance telemetry for optical transponder endpoints that complements fault/alarm signaling from `wdm_alert`.

## Topology binding source

Use `lookups/router_wdm_transponders.csv` as the mapping source for route and endpoint metadata.

Expected lookup orientation:

- `router_a`, `interface_a`, `transponder_a_eth`, `transponder_a_wdm`
- `router_z`, `interface_z`, `transponder_z_eth`, `transponder_z_wdm`

Records should preserve endpoint orientation (A or Z) deterministically.

## Required metric fields

Each endpoint record must carry these PM metrics:

- `LSBIASCUR` (Laser Bias Current, Tx side)
- `FEC_BEF_COR_ER` (Forward Error Correction Before Corrected Error, Rx side)
- `SUMOOPCUR` (Summarized Optical Output Power Current, Tx side)
- `SUMIOPCUR` (Summarized Optical Input Power Current, Rx side)
- `BDTEMPCUR` (Board Temperature Current)
- `EDTMPCUR` (Laser Temperature Current)

Observed statistics from all rows in `docs/wdm_pm_sample.csv` (required metrics only, no outlier filtering):

- `LSBIASCUR`: avg `25.3833`, min `10.3`, max `144.5` `mA`
- `FEC_BEF_COR_ER`: avg `0.2353`, min `0.0`, max `4.0` (unit blank in source CSV)
- `SUMOOPCUR`: avg `-40.2148`, min `-60.0`, max `10.5` `dBm`
- `SUMIOPCUR`: avg `-47.6562`, min `-60.0`, max `9.2` `dBm`
- `BDTEMPCUR`: avg `32.1145`, min `25.8`, max `47.0` `C`
- `EDTMPCUR`: avg `40.2202`, min `24.9`, max `46.6` `C`

Outlier-eliminated reference (group by endpoint path, then drop groups outside P5-P95 of per-endpoint avg):

- `LSBIASCUR`: avg `77.4969`, min `10.3`, max `144.5` `mA`
- `FEC_BEF_COR_ER`: avg `0.0000`, min `0.0`, max `0.0` (unit blank in source CSV)
- `SUMOOPCUR`: avg `-45.7914`, min `-60.0`, max `10.0` `dBm`
- `SUMIOPCUR`: avg `-50.9794`, min `-60.0`, max `-2.1` `dBm`
- `BDTEMPCUR`: avg `32.8375`, min `27.1`, max `36.0` `C`
- `EDTMPCUR`: avg `44.0509`, min `25.0`, max `46.1` `C`

## Semantics

- Tx metrics: `LSBIASCUR`, `SUMOOPCUR`
- Rx metrics: `FEC_BEF_COR_ER`, `SUMIOPCUR`
- Device context metrics: `BDTEMPCUR`, `EDTMPCUR`

Do not rename these metric keys; dashboards/searches depend on stable names.

## CSV guidance

For generator compatibility with project CSV handling:

- Keep the first line as the header.
- Keep data rows as templated body rows.
- Keep timestamp and endpoint identity fields explicit so `props.conf` time extraction and route joins remain stable.
