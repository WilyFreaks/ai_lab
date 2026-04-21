# Splunk app rules

Always read:
- docs/project_ai_lab.md
- docs/project_conf_design.md
- docs/project_script_design.md

When modifying Splunk configuration:
- Inspect existing files under default/
- Follow existing stanza naming patterns

Do not introduce new field names unless explicitly required.

For production data generators (`bin/launcher.py`, `bin/backfill_log.py`, `bin/live_log.py`):
- Keep weekend/weekday transition behavior smooth.
- Avoid abrupt value jumps at boundary times (notably Sunday 22:00-23:59 JST).
- Use interpolation windows around Fri→Sat and Sun→Mon transitions.