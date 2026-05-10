#!/usr/bin/env python3
"""
Hourly spool cleanup for ai_lab.

Invoked as a Splunk scripted input (interval = 3600).
Deletes files under var/spool/ai_lab/ whose mtime is older than
AGE_THRESHOLD_HOURS hours.  Preserves directory structure.

Emits a single JSON line to stdout so Splunk ingests it into
index=ai_lab_logs sourcetype=ai_lab:spool_cleanup.
"""

import json
import os
import sys
import time

AGE_THRESHOLD_HOURS = 4
SPOOL_ROOT_RELATIVE = os.path.join("var", "spool", "ai_lab")


def get_spool_root():
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(app_dir, SPOOL_ROOT_RELATIVE)


def main():
    spool_root = get_spool_root()
    now = time.time()
    cutoff = now - AGE_THRESHOLD_HOURS * 3600

    if not os.path.isdir(spool_root):
        print(json.dumps({
            "timestamp": int(now),
            "status": "skipped",
            "reason": "spool_root_not_found",
            "spool_root": spool_root,
            "deleted_count": 0,
            "error_count": 0,
        }))
        sys.exit(0)

    deleted = []
    errors = []

    for dirpath, _dirnames, filenames in os.walk(spool_root):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                mtime = os.path.getmtime(filepath)
                if mtime < cutoff:
                    os.remove(filepath)
                    deleted.append(os.path.relpath(filepath, spool_root))
            except OSError as exc:
                errors.append({"path": os.path.relpath(filepath, spool_root),
                                "error": str(exc)})

    print(json.dumps({
        "timestamp": int(now),
        "status": "ok",
        "spool_root": spool_root,
        "age_threshold_hours": AGE_THRESHOLD_HOURS,
        "deleted_count": len(deleted),
        "error_count": len(errors),
        "deleted_files": deleted,
        "errors": errors,
    }))


if __name__ == "__main__":
    main()
