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

Daily journaling:
- Maintain `docs/daily_activity_timeline.md` as the project daily journal.
- When a meaningful work session finishes, append/update the day section with:
  - session time (use "around" wording unless exact per-message timestamp exists)
  - key activities and decisions
  - important follow-up actions
- Do not fabricate exact timestamps when only session-level metadata exists.

Session boundary rule for journaling:
- Treat a new user input after **> 1 hour** of inactivity as a **new session start**.
- Treat **> 1 hour** with no user input as the **previous session end**.
- Use the **last observed user input timestamp** as session end time.
- Log each session in `docs/daily_activity_timeline.md` with:
  - start time
  - end time
  - brief activity summary
  - Resume anchor (infer the most appropriate next restart point from the user's latest inputs in that session)
- If exact per-message timestamps are unavailable, fall back to "around" wording and note metadata limits.
- If a session crosses midnight (JST), split it into two day entries:
  - previous day ends at around `23:59 JST`
  - next day starts at around `00:00 JST` (mark as carry-over if helpful)
- Always update `docs/daily_activity_timeline.md` at session boundary events so journaling stays current.
- In `## Observable Duration and Estimated Token Usage`, compute each day's duration as the **sum of logged session timeline ranges** for that day (for example `05:03-05:58` = 55 min), not token-derived duration.
- Use token estimates only for the "Estimated Tokens" values.
- To reduce editor Keep/Undo prompts, avoid per-message journaling writes.
- Update `docs/daily_activity_timeline.md` at checkpoints:
  - session boundary events (session start/end by `> 1 hour` inactivity)
  - day rollover split (`23:59` / `00:00` JST)
  - user shutdown/sleep notes (treat as session-close checkpoint)
  - explicit user request to refresh the timeline
  - optional periodic checkpoint about every 15-30 minutes during long active sessions
- At each checkpoint update, synchronize both:
  - the current session header time range (`<start_time>-<end_time>`)
  - the `### Daily summary` entry for the current day
- Keep timeline ordering in `docs/daily_activity_timeline.md` as **newest to oldest** for both:
  - day sections
  - `### Daily summary` bullet list
- In `### Daily summary`, do not add the word "observed"; format as:
  - `YYYY-MM-DD: <duration> (<start-end>), <tokens> estimated tokens`