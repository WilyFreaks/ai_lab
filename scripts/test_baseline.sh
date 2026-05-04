#!/usr/bin/env bash
set -euo pipefail

# Canonical baseline data-quality test entrypoint.
# This validates baseline behavior (telemetry, TWAMP saved searches
# twamp_event_count_test / twamp_dmean_test / twamp_jmean_test,
# cnc_service_health_json, etc.) whether data came from backfill, live, or both.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/test_backfill.sh" "$@"
