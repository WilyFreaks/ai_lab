#!/usr/bin/env python3
"""Merge local/savedsearches.conf into default/savedsearches.conf (Splunk-style).

Per-stanza: preserve default-only stanzas and keys; overlay keys present in local
(local wins). Stanzas that exist only in local are appended after all default
stanzas. Multiline keys (trailing ``\\`` continuation) are kept as raw line
blocks so SPL formatting matches the source file.

Usage:
  python3 scripts/merge_local_savedsearches_to_default.py [--dry-run] [--app-root PATH]

After merging (or to compare before/after snapshots), dump the effective layer::

  export SPLUNK_HOME=/opt/splunk   # or your install, e.g. /Applications/Splunk
  /opt/splunk/bin/splunk btool savedsearches list --app=ai_lab > /tmp/btool.txt

Do **not** ``LC_ALL=C sort`` the whole file (SPL lines from different searches
get mixed). A raw ``diff`` of the full list can also show harmless extra leading
``[ search ...]`` multi-line blocks depending on merge/order — compare **per
saved-search** instead: split on single-line stanza headers ``^[...]$`` (name
in brackets on one line) and ``diff`` each block, or assert the same set of
stanza names and identical bodies for each.
"""
from __future__ import annotations

import argparse
import sys
from collections import OrderedDict
from pathlib import Path


def _is_stanza_header(raw: str) -> tuple[bool, str]:
    """Return (True, name) if raw is a Splunk stanza header line: starts at col 0,
    matches [name] with no leading whitespace.  Indented lines like
    '    [ search index=... ]' inside SPL are NOT stanza headers."""
    if not raw.startswith("["):
        return False, ""
    stripped = raw.strip()
    if stripped.startswith("[") and stripped.endswith("]") and "\n" not in stripped:
        name = stripped[1:-1]
        # Reject if the name itself looks like SPL (contains spaces + keywords)
        # A real stanza name never starts with a space after '['
        if not stripped[1:2] == " ":
            return True, name
    return False, ""


def parse_savedsearches(path: Path) -> OrderedDict[str, list[tuple[str, list[str]]]]:
    """Return stanza name -> ordered list of (key, physical_lines for that key).

    Multiline values (lines ending with ``\\``) are collected in full so SPL
    blocks like ``| union [ search ... ] [ search ... ]`` are kept intact.
    Stanza headers must start at column 0; indented ``[ search ... ]`` lines
    inside SPL are NOT treated as headers.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    stanzas: OrderedDict[str, list[tuple[str, list[str]]]] = OrderedDict()
    cur: str | None = None
    i = 0
    while i < len(lines):
        raw = lines[i]
        is_hdr, name = _is_stanza_header(raw)
        if is_hdr:
            cur = name
            if cur not in stanzas:
                stanzas[cur] = []
            i += 1
            continue
        if cur is None:
            i += 1
            continue
        if not raw.strip():
            i += 1
            continue
        # Only start a new key if this line is at col-0 and contains '='
        # (i.e. not an indented continuation that happens to have '=')
        if not raw.startswith(" ") and not raw.startswith("\t") and "=" in raw:
            key = raw.split("=", 1)[0].strip()
            block = [raw]
            i += 1
            # Collect continuation lines: keep going while the previous
            # collected line ends with '\', regardless of what the next
            # line looks like (could be indented SPL, could start with '[')
            while i < len(lines):
                prev = block[-1]
                if prev.rstrip().endswith("\\"):
                    block.append(lines[i])
                    i += 1
                else:
                    break
            stanzas[cur].append((key, block))
        else:
            # Indented line with no active continuation — skip (blank or orphan)
            i += 1
    return stanzas


def blocks_to_keymap(blocks: list[tuple[str, list[str]]]) -> OrderedDict[str, list[str]]:
    m: OrderedDict[str, list[str]] = OrderedDict()
    for k, bl in blocks:
        m[k] = bl
    return m


def merge_stanza(
    default_blocks: list[tuple[str, list[str]]],
    local_blocks: list[tuple[str, list[str]]] | None,
) -> list[tuple[str, list[str]]]:
    if not local_blocks:
        return list(default_blocks)
    local_map = blocks_to_keymap(local_blocks)
    default_keys = {k for k, _ in default_blocks}
    out: list[tuple[str, list[str]]] = []
    for k, bl in default_blocks:
        if k in local_map:
            out.append((k, list(local_map[k])))
        else:
            out.append((k, list(bl)))
    for k, bl in local_blocks:
        if k not in default_keys:
            out.append((k, list(bl)))
    return out


def merge_all(
    default_path: Path,
    local_path: Path,
) -> OrderedDict[str, list[tuple[str, list[str]]]]:
    d = parse_savedsearches(default_path)
    if not local_path.is_file():
        return d
    l = parse_savedsearches(local_path)
    out: OrderedDict[str, list[tuple[str, list[str]]]] = OrderedDict()
    for name, blocks in d.items():
        out[name] = merge_stanza(blocks, l.get(name))
    for name, blocks in l.items():
        if name not in out:
            out[name] = list(blocks)
    return out


def emit(merged: OrderedDict[str, list[tuple[str, list[str]]]]) -> str:
    parts: list[str] = []
    names = list(merged.keys())
    for idx, name in enumerate(names):
        parts.append(f"[{name}]")
        for _k, block_lines in merged[name]:
            parts.extend(block_lines)
        if idx < len(names) - 1:
            parts.append("")
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="ai_lab app root (parent of default/ and local/)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diff summary only; do not write default/savedsearches.conf",
    )
    args = ap.parse_args()
    app = args.app_root.resolve()
    default_conf = app / "default" / "savedsearches.conf"
    local_conf = app / "local" / "savedsearches.conf"
    if not default_conf.is_file():
        print(f"ERROR: missing {default_conf}", file=sys.stderr)
        return 1
    if not local_conf.is_file():
        print(f"SKIP: no {local_conf}")
        return 0
    merged = merge_all(default_conf, local_conf)
    body = emit(merged)
    if args.dry_run:
        old = default_conf.read_text(encoding="utf-8", errors="replace")
        if old == body:
            print("merge result identical to current default/savedsearches.conf")
        else:
            old_n = len(old.splitlines())
            new_n = len(body.splitlines())
            print(f"would write default/savedsearches.conf ({old_n} -> {new_n} lines)")
        return 0
    default_conf.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {default_conf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
