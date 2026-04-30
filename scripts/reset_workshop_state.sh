#!/usr/bin/env bash
set -euo pipefail

# Reset workshop runtime state:
# 1) stop Splunk
# 2) delete ai_lab index directories (derived from default/indexes.conf)
# 3) delete all files under app var/spool (monitored spool JSON, etc.)
# 4) delete local/ai_lab_scenarios.conf
# 5) start Splunk

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Default to Linux-style install path. Override with SPLUNK_HOME when needed.
SPLUNK_HOME="${SPLUNK_HOME:-/opt/splunk}"
SPLUNK_BIN="$SPLUNK_HOME/bin/splunk"
INDEX_CONF="$APP_ROOT/default/indexes.conf"
LOCAL_SCENARIO_CONF="$APP_ROOT/local/ai_lab_scenarios.conf"
SPLUNK_DB="$SPLUNK_HOME/var/lib/splunk"
SPOOL_ROOTS=(
  "$APP_ROOT/var/spool/ai_lab"
)
SPLUNK_AUTH="${SPLUNK_AUTH:-}"
SPLUNK_TOKEN="${SPLUNK_TOKEN:-${AUTH_TOKEN:-}}"

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
echo "- Delete all files under app var/spool (workshop spool JSON, etc.):"
for _sr in "${SPOOL_ROOTS[@]}"; do
  printf '  - %s\n' "$_sr"
done
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

echo "Removing all spool files under var/spool..."
_seen_realpaths=()
for SPOOL_ROOT in "${SPOOL_ROOTS[@]}"; do
  if [[ ! -d "$SPOOL_ROOT" ]]; then
    echo "  skip (not found): $SPOOL_ROOT"
    continue
  fi
  if ! ensure_path_under_base "$SPOOL_ROOT" "$APP_ROOT"; then
    echo "ERROR: Refusing to delete spool path outside app roots: $SPOOL_ROOT"
    exit 1
  fi
  rp="$(realpath_py "$SPOOL_ROOT")"
  dup="false"
  for prev in "${_seen_realpaths[@]+"${_seen_realpaths[@]}"}"; do
    if [[ "$prev" == "$rp" ]]; then
      dup="true"
      break
    fi
  done
  if [[ "$dup" == "true" ]]; then
    echo "  skip (same path as earlier): $SPOOL_ROOT"
    continue
  fi
  _seen_realpaths+=("$rp")
  # All files under var/spool (e.g. workshop_region JSON); keep the var/spool directory.
  fc="$(find "$SPOOL_ROOT" -type f 2>/dev/null | wc -l | tr -d '[:space:]')"
  find "$SPOOL_ROOT" -type f -delete 2>/dev/null || true
  for ((_i = 0; _i < 100; _i++)); do
    n="$(find "$SPOOL_ROOT" -mindepth 1 -type d -empty 2>/dev/null | wc -l | tr -d '[:space:]')"
    [[ "${n:-0}" -eq 0 ]] && break
    find "$SPOOL_ROOT" -mindepth 1 -type d -empty -delete 2>/dev/null || break
  done
  echo "  removed ${fc:-0} file(s) under $SPOOL_ROOT (empty dirs pruned)"
done

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
if [[ -z "$SPLUNK_AUTH" && -z "$SPLUNK_TOKEN" ]]; then
  echo "ERROR: SPLUNK_AUTH or SPLUNK_TOKEN is required for verification."
  echo "       Examples:"
  echo "         export SPLUNK_AUTH='admin:changeme'"
  echo "         export SPLUNK_TOKEN='<mcp bearer token>'"
  exit 1
fi

for idx in "${APP_INDEXES[@]}"; do
  query="index=$idx earliest=0 latest=now | stats count"
  if [[ -n "$SPLUNK_TOKEN" ]]; then
    if ! count="$("$SPLUNK_BIN" search "$query" -token "$SPLUNK_TOKEN" | extract_count)"; then
      echo "ERROR: Verification search failed for index '$idx'"
      exit 1
    fi
  else
    if ! count="$("$SPLUNK_BIN" search "$query" -auth "$SPLUNK_AUTH" | extract_count)"; then
      echo "ERROR: Verification search failed for index '$idx'"
      exit 1
    fi
  fi
  if (( count != 0 )); then
    echo "ERROR: Index '$idx' still has events: $count"
    exit 1
  fi
  echo "  verified empty: $idx"
done

echo "Done."
