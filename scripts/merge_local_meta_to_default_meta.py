#!/usr/bin/env python3
"""Merge metadata/local.meta into metadata/default.meta for workshop packaging.

- Keeps comments / preamble from default.meta through the line before the first stanza.
- Merges stanza blocks from local.meta into default.meta (same stanza name replaces).
- Omits [savedsearches/...] entries when no matching stanza exists in
  default/savedsearches.conf (after URL-decoding the suffix).
- Rewrites ``owner = admin`` -> ``owner = nobody`` in merged-local bodies.

If metadata/local.meta is missing, exits 0 after printing skip (no-op).
If metadata/default.meta is missing, exits 1.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote_plus


def parse_meta_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^\[([^\]]*)\]\s*$", lines[i])
        if m:
            name = m.group(1)
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and not re.match(r"^\[", lines[i]):
                body_lines.append(lines[i])
                i += 1
            blocks.append((name, "\n".join(body_lines).rstrip("\n")))
        else:
            i += 1
    return blocks


def split_preamble(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    idx = 0
    while idx < len(lines) and (lines[idx].strip() == "" or lines[idx].startswith("#")):
        idx += 1
    return "".join(lines[:idx]), "".join(lines[idx:])


def normalize_owner(body: str) -> str:
    out: list[str] = []
    for line in body.splitlines():
        if line.strip() == "owner = admin":
            out.append("owner = nobody")
        else:
            out.append(line)
    return "\n".join(out).rstrip("\n")


def load_savedsearch_stanza_names(savedsearches_conf: Path) -> set[str]:
    text = savedsearches_conf.read_text(encoding="utf-8")
    names = set()
    for m in re.finditer(r"^\[([^\]]+)\]\s*$", text, re.MULTILINE):
        names.add(m.group(1))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="ai_lab app root (parent of metadata/, default/)",
    )
    args = parser.parse_args()
    app_root: Path = args.app_root

    local_meta = app_root / "metadata" / "local.meta"
    default_meta = app_root / "metadata" / "default.meta"
    ss_conf = app_root / "default" / "savedsearches.conf"

    if not default_meta.is_file():
        print(f"ERROR: Missing {default_meta}", file=sys.stderr)
        return 1

    if not local_meta.is_file():
        print(f"  skip (not found): {local_meta}")
        return 0

    if not ss_conf.is_file():
        print(f"ERROR: Missing {ss_conf} (cannot validate savedsearches metadata)", file=sys.stderr)
        return 1

    default_text = default_meta.read_text(encoding="utf-8")
    local_text = local_meta.read_text(encoding="utf-8")
    ss_names = load_savedsearch_stanza_names(ss_conf)

    pref, default_rest = split_preamble(default_text)
    default_blocks = parse_meta_blocks(default_rest)
    local_blocks = parse_meta_blocks(local_text)

    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, body in default_blocks:
        merged.append((name, body))
        seen.add(name)

    omitted = 0
    for name, body in local_blocks:
        if name.startswith("savedsearches/"):
            suffix = name[len("savedsearches/") :]
            decoded = unquote_plus(suffix)
            if decoded not in ss_names and suffix not in ss_names:
                omitted += 1
                continue
        body = normalize_owner(body)
        if name in seen:
            merged = [(n, b) for n, b in merged if n != name]
            merged.append((name, body))
        else:
            merged.append((name, body))
            seen.add(name)

    out_lines = [pref.rstrip("\n")]
    for name, body in merged:
        out_lines.append("")
        out_lines.append(f"[{name}]")
        if body:
            out_lines.extend(body.splitlines())

    final = "\n".join(out_lines)
    if not final.endswith("\n"):
        final += "\n"

    default_meta.write_text(final, encoding="utf-8")
    print(f"  merged: {local_meta} -> {default_meta}")
    if omitted:
        print(f"    omitted {omitted} savedsearches stanza(s) with no matching default/savedsearches.conf entry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
