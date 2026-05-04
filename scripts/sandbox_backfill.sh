#!/usr/bin/env bash
# Dry-run backfill into an isolated directory (does not use app local/ or var/spool).
#
# Usage:
#   bash scripts/sandbox_backfill.sh
#   AI_LAB_SANDBOX_ROOT=/path AI_LAB_SANDBOX_WINDOW_MINUTES=10 bash scripts/sandbox_backfill.sh
#
# Output: spool files under $AI_LAB_SANDBOX_ROOT/spool/ai_lab/

set -euo pipefail

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_ROOT"

if [[ -z "${AI_LAB_SANDBOX_ROOT:-}" ]]; then
  AI_LAB_SANDBOX_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ai_lab_sandbox.XXXXXX")"
  export AI_LAB_SANDBOX_ROOT
  echo "Using temp sandbox: $AI_LAB_SANDBOX_ROOT"
fi

mkdir -p "$AI_LAB_SANDBOX_ROOT"

# Short window keeps artifacts small (TWAMP uses 10s steps).
: "${AI_LAB_SANDBOX_WINDOW_MINUTES:=5}"
export AI_LAB_SANDBOX_WINDOW_MINUTES

NOW="$(date +%s)"
REGION="${AI_LAB_SANDBOX_REGION:-au}"

CONF_PATH="$AI_LAB_SANDBOX_ROOT/ai_lab_scenarios.conf"
cat >"$CONF_PATH" <<EOF
[baseline]
region = $REGION
backfill_start_time = $NOW
backfill_completed = false
baseline_generation_enabled = true
EOF

python3 bin/backfill_log.py

echo ""
echo "Sandbox state: $CONF_PATH"
echo "Spool output:"
find "$AI_LAB_SANDBOX_ROOT/spool" -type f 2>/dev/null | head -50 || true
echo ""
echo "TWAMP sample (first 3 lines of first .csv):"
TWAMP_CSV="$(find "$AI_LAB_SANDBOX_ROOT/spool/ai_lab/twamp" -name '*.csv' -type f 2>/dev/null | head -1 || true)"
if [[ -n "$TWAMP_CSV" ]]; then
  head -n 3 "$TWAMP_CSV"
else
  echo "(no twamp csv found)"
fi
