#!/usr/bin/env bash
set -euo pipefail

# Canonical baseline data-quality test entrypoint.
# Runs scripts/test_backfill.sh: telemetry, TWAMP (twamp_event_count / twamp_dmean / twamp_jmean),
# cnc_service_health_json, etc., plus assert_thousandeyes_trend_per_day (trend_per_day vs
# backfill_head_time on ThousandEyes raw samples). Use either script; behaviour is the same.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/test_backfill.sh" "$@"
