# `syslog` / `wdm_alert` sample contract

This sample represents the WDM issue signal used in the workshop scenario.

## Purpose

- Sourcetype: `wdm_alert`
- Payload shape: XML (`sample.xml`)
- Role: indicate the optical transport fault condition (for example LOS / transponder issue) in the syslog stream.

## Key placeholders

- `{{sequence}}` -> unique notification/event id
- `{{timestamp}}` -> domain event time for `<source-time>` (ISO-8601 with numeric offset)

## Host extraction contract

- Event host must be extracted from the Native EMS alias pair:
  - `<alias-name>NativeEMSName</alias-name>`
  - `<alias-value>R7</alias-value>`
- In this example, host becomes `R7`.

Index-time config expected in app defaults:

- `props.conf` stanza: `[wdm_alert]`
- `props.conf`: `TRANSFORMS-set_host = set_host_from_wdm_alert_xml`
- `transforms.conf` stanza: `[set_host_from_wdm_alert_xml]`
  - Regex captures `<alias-value>` for `NativeEMSName`
  - `DEST_KEY = MetaData:Host`

## Notes

- Keep this payload as single-event XML (one alarm object per generated event).
- Preserve the alias-name/alias-value structure because host extraction depends on it.
