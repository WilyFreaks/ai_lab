# ai_lab Tests

## Canonical command

```bash
bash tests/smoke/test_smoke.sh
```

This is the single smoke-test entrypoint for local and Cursor-driven runs.

## Required environment

- `SPLUNK_AUTH` (required for SPL checks), example:

```bash
export SPLUNK_AUTH="admin:p4ssw0rd"
```

Optional:

- `SPLUNK_HOME` (defaults to `/opt/splunk`). Use your real install path on macOS, e.g. `export SPLUNK_HOME=/Applications/Splunk`, for `scripts/reset_workshop_state.sh` and any CLI that assumes `$SPLUNK_HOME`.
- `SPLUNK_APP` (defaults to `ai_lab`)
- `TIME_WINDOW` for SPL checks (defaults to `24h`)
- `SPLUNK_PYTHON` to override the interpreter used for py_compile

## What smoke test runs

1. Python syntax/compile checks for app scripts
2. Runtime precondition checks for required files
3. SPL assertions via `tests/splunk/run_spl_checks.sh`

## SPL assertions

- all app indexes from `default/indexes.conf` are empty (hard precondition)
- if `alerts` exists, it is included in the empty-index precondition (it may be empty in a clean workshop)
- if `episode` exists, it is included in the empty-index precondition (it may be empty in a clean workshop)
- parser/JSON errors are zero in `_internal` for relevant ingest paths

## Documentation ownership

- App/project behavior and test contract:
  - `docs/project_ai_lab.md`
  - `docs/project_test_design.md`
- SPL-specific conventions and review rules:
  - `~/.cursor/skills-cursor/splunk-search-assistant/SKILL.md`
