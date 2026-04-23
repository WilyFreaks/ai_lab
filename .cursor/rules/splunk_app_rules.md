# Splunk app rules

Always read:
- docs/project_ai_lab.md
- docs/project_conf_design.md
- docs/project_script_design.md
- docs/project_dashboard_design.md
- docs/project_scenario_*.md

When modifying Splunk configuration:
- Inspect existing files under default/
- Follow existing stanza naming patterns

Do not introduce new field names unless explicitly required.

`local/` policy (important for workshop test runs):
- Do not automatically update files under `local/`.
- Treat `local/ai_lab_scenarios.conf` as test-owned state managed by Splunk/test flow.
- Agent/code changes must target `default/` and docs, not pre-populate or mutate `local/` content.

For production data generators (`bin/launcher.py`, `bin/backfill_log.py`, `bin/live_log.py`):
- Keep weekend/weekday transition behavior smooth.
- Avoid abrupt value jumps at boundary times (notably Sunday 22:00-23:59 JST).
- Use interpolation windows around Fri→Sat and Sun→Mon transitions.