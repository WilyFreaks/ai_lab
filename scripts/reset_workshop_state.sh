#!/usr/bin/env bash
set -euo pipefail

# Reset workshop runtime state:
# 1) stop Splunk
# 2) delete ai_lab index directories (derived from default/indexes.conf)
# 3) delete local/ai_lab_scenarios.conf
# 4) start Splunk

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Default to Linux-style install path. Override with SPLUNK_HOME when needed.
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
INDEX_CONF="$APP_ROOT/default/indexes.conf"
LOCAL_SCENARIO_CONF="$APP_ROOT/local/ai_lab_scenarios.conf"
SPLUNK_DB="$SPLUNK_HOME/var/lib/splunk"
SPLUNK_APP_HOME="$SPLUNK_HOME/etc/apps/ai_lab"
SPOOL_ROOT="$SPLUNK_APP_HOME/var/spool/ai_lab"
SPLUNK_AUTH="${SPLUNK_AUTH:-}"

ASSUME_YES="false"
if [[ "${1:-}" == "--yes" ]]; then
  ASSUME_YES="true"
fi

if [[ ! -x "$SPLUNK_BIN" ]]; then
  echo "ERROR: Splunk CLI not found at: $SPLUNK_BIN"
  exit 1
fi

if [[ ! -f "$INDEX_CONF" ]]; then
  echo "ERROR: Index config not found: $INDEX_CONF"
  exit 1
fi

if [[ -z "$SPLUNK_DB" || "$SPLUNK_DB" == "/" || "$SPLUNK_DB" == "." || "$SPLUNK_DB" == ".." ]]; then
  echo "ERROR: Unsafe SPLUNK_DB value: '$SPLUNK_DB'"
  exit 1
fi

if [[ ! -d "$SPLUNK_DB" ]]; then
  echo "ERROR: SPLUNK_DB directory not found: $SPLUNK_DB"
  exit 1
fi

APP_INDEXES=()
while IFS= read -r idx; do
  APP_INDEXES+=("$idx")
done < <(awk '
  /^\[/ && /\]$/ {
    name=$0
    gsub(/^\[/, "", name)
    gsub(/\]$/, "", name)
    if (name != "") print name
  }
' "$INDEX_CONF")

if [[ "${#APP_INDEXES[@]}" -eq 0 ]]; then
  echo "ERROR: No indexes found in $INDEX_CONF"
  exit 1
fi

is_safe_index_name() {
  local name="$1"
  # Allow typical Splunk index names; reject path-like or dangerous values.
  [[ "$name" =~ ^[A-Za-z0-9_:-]+$ ]] || return 1
  [[ "$name" != "." && "$name" != ".." ]] || return 1
  return 0
}

realpath_py() {
  python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

ensure_path_under_base() {
  local target="$1"
  local base="$2"
  local target_real
  local base_real
  target_real="$(realpath_py "$target")"
  base_real="$(realpath_py "$base")"
  if [[ "$target_real" != "$base_real"/* ]]; then
    return 1
  fi
  return 0
}

echo "Reset plan:"
echo "- Stop Splunk"
echo "- Delete index directories and .dat files under $SPLUNK_DB for:"
printf '  - %s\n' "${APP_INDEXES[@]}"
echo "- Delete monitored spool JSON files under $SPOOL_ROOT"
echo "- Delete $LOCAL_SCENARIO_CONF (if present)"
echo "- Start Splunk"

if [[ "$ASSUME_YES" != "true" ]]; then
  read -r -p "Proceed? (yes/no): " REPLY
  if [[ "$REPLY" != "yes" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

echo "Stopping Splunk..."
"$SPLUNK_BIN" stop

echo "Removing index data directories and .dat files..."
for idx in "${APP_INDEXES[@]}"; do
  if ! is_safe_index_name "$idx"; then
    echo "ERROR: Unsafe index name from indexes.conf: '$idx'"
    exit 1
  fi

  idx_path="$SPLUNK_DB/$idx"
  idx_dat_path="$SPLUNK_DB/$idx.dat"

  # Defense-in-depth: ensure resolved targets stay under SPLUNK_DB.
  if ! ensure_path_under_base "$idx_path" "$SPLUNK_DB"; then
    echo "ERROR: Refusing to delete path outside SPLUNK_DB: $idx_path"
    exit 1
  fi
  if ! ensure_path_under_base "$idx_dat_path" "$SPLUNK_DB"; then
    echo "ERROR: Refusing to delete path outside SPLUNK_DB: $idx_dat_path"
    exit 1
  fi

  if [[ -d "$idx_path" ]]; then
    rm -rf "$idx_path"
    echo "  removed: $idx_path"
  else
    echo "  skip (not found): $idx_path"
  fi

  if [[ -f "$idx_dat_path" ]]; then
    rm -f "$idx_dat_path"
    echo "  removed: $idx_dat_path"
  else
    echo "  skip (not found): $idx_dat_path"
  fi
done

echo "Removing monitored spool files..."
if [[ -d "$SPOOL_ROOT" ]]; then
  if ! ensure_path_under_base "$SPOOL_ROOT" "$SPLUNK_APP_HOME"; then
    echo "ERROR: Refusing to delete spool path outside app home: $SPOOL_ROOT"
    exit 1
  fi
  rm -rf "$SPOOL_ROOT"
  echo "  removed: $SPOOL_ROOT"
else
  echo "  skip (not found): $SPOOL_ROOT"
fi

if [[ -f "$LOCAL_SCENARIO_CONF" ]]; then
  if ! ensure_path_under_base "$LOCAL_SCENARIO_CONF" "$APP_ROOT"; then
    echo "ERROR: Refusing to delete local scenario path outside app root: $LOCAL_SCENARIO_CONF"
    exit 1
  fi
  rm -f "$LOCAL_SCENARIO_CONF"
  echo "Removed: $LOCAL_SCENARIO_CONF"
else
  echo "Skip (not found): $LOCAL_SCENARIO_CONF"
fi

echo "Starting Splunk..."
"$SPLUNK_BIN" start

extract_count() {
  awk '
    /^[[:space:]]*[0-9]+[[:space:]]*$/ { val=$1 }
    END {
      if (val == "") exit 1
      print val
    }
  '
}

echo "Verifying index data deletion with SPL..."
if [[ -z "$SPLUNK_AUTH" ]]; then
  echo "ERROR: SPLUNK_AUTH is required for verification (example: export SPLUNK_AUTH='admin:changeme')"
  exit 1
fi

for idx in "${APP_INDEXES[@]}"; do
  query="index=$idx earliest=0 latest=now | stats count"
  if ! count="$("$SPLUNK_BIN" search "$query" -auth "$SPLUNK_AUTH" | extract_count)"; then
    echo "ERROR: Verification search failed for index '$idx'"
    exit 1
  fi
  if (( count != 0 )); then
    echo "ERROR: Index '$idx' still has events: $count"
    exit 1
  fi
  echo "  verified empty: $idx"
done

echo "Done."
