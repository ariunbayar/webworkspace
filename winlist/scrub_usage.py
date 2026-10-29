#!/usr/bin/env python3
"""One-off: mask what the usage log spelled out before #41.

Run:  python3 winlist/scrub_usage.py            # backs up, then rewrites the log
      python3 winlist/scrub_usage.py --dry-run  # only says how many it would mask

Until #41 the page logged keys typed into a group's name or folder one by one,
so a run of them spelled the text out. usage_report.mask_typing() decides what
was typing; this writes its answer back to the file, keeping every other line
and field as it was. The original is kept beside it as usage.jsonl.bak-<time>.
"""
import argparse
import json
import os
import shutil
import time

from usage_report import LOG, mask_typing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=LOG)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    with open(args.log) as f:
        lines = f.readlines()
    parsed = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            e = None
        parsed.append(e if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) else None)
    n = mask_typing([e for e in parsed if e])
    print("%d key events masked of %d lines" % (n, len(lines)))
    if args.dry_run or not n:
        return
    backup = "%s.bak-%s" % (args.log, time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(args.log, backup)
    tmp = args.log + ".tmp"
    with open(tmp, "w") as f:
        for line, e in zip(lines, parsed):
            f.write(json.dumps(e, separators=(",", ":")) + "\n" if e else line)
    os.replace(tmp, args.log)
    print("backed up to %s" % backup)


if __name__ == "__main__":
    main()
