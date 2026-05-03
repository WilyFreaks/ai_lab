#!/usr/bin/env bash
set -euo pipefail

# Canonical baseline data-quality test entrypoint.
# This validates baseline behavior (including cnc_service_health_json
# cnc_service_health_test assertions) regardless of whether data came from
# backfill generation, live generation, or a mix of both.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/test_backfill.sh" "$@"
