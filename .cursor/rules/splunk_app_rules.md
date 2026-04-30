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

`docs/daily_activity_timeline.md` journaling (user-controlled):
- This file is the project daily journal, but is updated **only when the user explicitly requests** an update to `docs/daily_activity_timeline.md` (no proactive edits).

Update triggers (phrases the user can use):
- "resume session": treat this as a **correction signal** for the **active session’s start time** (JST). If the user states a time, use it; otherwise set start time using the precedence below. Do **not** invent a “nice” start time that overlaps the previous session’s end time.
- "update @docs/daily_activity_timeline.md" / "update docs/daily_activity_timeline.md": perform a **timeline checkpoint update** for the day: refresh session text, and set/refresh the **active session’s end time** using the precedence below (unless the user says the session is still ongoing / asks for a partial update only).
- "anchor" / "anchor the next action": set/refresh the **Resume anchor** for the active session. If the session header is still single-time, convert it to range form per the anchor keyword rule.
- Anchor keyword rule: when the user says "anchor" (or uses phrasing like "anchor the next action"), update the current session header from single-time format to range format: `Session N around **<start>-<end> JST**`.

Time selection precedence (JST, use "around" when uncertain):
- Prefer an **explicit time given by the user** in the same message (for example: "I resumed at 16:45").
- Else prefer **embedded per-message `<timestamp>` markers** in the chat (when available).
- Else use the **system clock** in JST (only as a best-effort fallback; do not present it as a precise user-provided time).

Session model (for grouping; does not auto-write the file):
- If there is a **> 1 hour** gap between user messages, start a **new session** in the journal on the next explicit timeline update (unless the user defines sessions differently in their update request).
- If a session crosses midnight (JST), split it across day sections as needed (carry-over is OK to note).

Content requirements for each session entry:
- Start and end time (range form once anchored)
- Brief activity summary and decisions
- Resume anchor (next concrete action)

Durations and summaries:
- In `## Observable Duration and Estimated Token Usage`, compute each day's `Observable Duration` as the **sum of the logged per-session JST time ranges** for that day, not a single first-message-to-last-message span.
- In that same section, the parenthetical should summarize workload as **`(N sessions)`** (session count for that day), not an expanded list of time ranges.
- Keep the `### Daily summary` line and the **table row** for the same date consistent (same minutes, same `N`, same token estimate).
- Use token estimates only for the "Estimated Tokens" values.
- Keep day sections and `### Daily summary` ordered **newest to oldest** (in the day section, newest session block first).
- In `### Daily summary`, do not add the word "observed"; format as: `YYYY-MM-DD: <duration> (N sessions), <tokens> estimated tokens` (duration should reflect the per-session sum rule above; use a session count parenthetical, not an expanded sum of time ranges).

`reset_workshop_state.sh` run rules:
- For unattended runs, execute `./scripts/reset_workshop_state.sh --yes` (avoid interactive `Proceed? (yes/no)` waits).
- Prefer token-based verification auth, not username/password.
- Read the token from Cursor MCP config (`~/.cursor/mcp.json` -> `mcpServers.splunk-mcp-server.env.AUTH_TOKEN`).
- Export token as `SPLUNK_TOKEN` (or rely on `AUTH_TOKEN`) before running verification.
- Use `SPLUNK_AUTH` (`user:pass`) only as fallback when token auth is unavailable.
- If a reset run appears slow/hung, first verify whether it is waiting for prompt input, then check `/opt/splunk/var/log/splunk/splunkd.log` for actual stop/start activity.

Splunk Simple XML `fieldset` visibility:
- `<fieldset>` only supports `autoRun` and `submitButton` (not `depends`). To show or hide the whole form input block (including Submit), wrap it in `<row depends="$token$">` (or use `depends` / `rejects` on `<input>` per input docs).

Splunk Simple XML `depends` and search execution:
- `depends` on a `<row>` or `<panel>` controls **visual visibility only**. The panel's search still executes when its token dependencies are satisfied, even if the row is hidden.
- `autoRun="false"` on `<fieldset>` defers **all** panel searches until the Submit button is clicked — regardless of whether their query tokens are form inputs or not. A hidden panel's search runs on Submit as long as its query tokens are set. If the Submit button is never clicked (e.g. locked state where fieldset is hidden), no panel search will ever run. In that case, trigger Submit programmatically in JS: `setTimeout(function(){ $(".fieldset button.btn.btn-primary").trigger("click"); }, 100);`

Splunk Simple XML `search/done` token action rule:
- In dashboard `search` `done` handlers, prefer wrapping token actions under `<condition>` blocks (for example `<condition match="true()"> ... </condition>`), and place `<set>/<unset>` inside those conditions.
- If editor warnings show `Invalid child="set" is not allowed in node="search-done"`, refactor direct `<set>/<unset>` siblings under `<done>` into `<condition>` blocks.