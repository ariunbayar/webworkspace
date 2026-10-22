#!/usr/bin/env python3
"""What winlist has been used for, from the log the page keeps.

Run:  python3 winlist/usage_report.py                 # every day there is
      python3 winlist/usage_report.py --days 7        # the last week
      python3 winlist/usage_report.py --split 2026-10-23  # before vs after a date

The page sends one line per thing done to /api/usage, and winlist_server.py
appends them to ~/.local/state/winlist/usage.jsonl: action names, the kind of
tile, the mode — never a title, a URL or anything typed. This turns them back
into numbers a person can compare: per day, and per day on each side of a date
when you want to know whether a change made a difference.
"""
import argparse
import collections
import datetime
import json
import os
import statistics

LOG = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                   "winlist", "usage.jsonl")


def load(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and isinstance(e.get("t"), (int, float)):
                    e["day"] = datetime.datetime.fromtimestamp(e["t"] / 1000).date()
                    out.append(e)
    except OSError:
        pass
    return out


def name(e):
    """An event as it reads in a table: a key with its mode, an action with its kind."""
    if e["ev"] == "key":
        return "key %s (%s)" % (e.get("k", "?"), e.get("mode", "?"))
    if "kind" in e:
        return "%s %s" % (e["ev"], e["kind"])
    return e["ev"]


def active_minutes(events):
    """Minutes with at least one thing done, per session: time actually spent."""
    return len({(e.get("s"), int(e["t"] // 60000)) for e in events if e["ev"] != "close"})


def summary(events, label, days):
    days = max(1, days)
    sessions = {e.get("s") for e in events}
    print("\n== %s: %d events, %d page loads, %d active minutes over %d day(s)"
          % (label, len(events), len(sessions), active_minutes(events), days))
    if not events:
        return {}
    counts = collections.Counter(name(e) for e in events)
    print("   %-38s %7s %9s" % ("action", "count", "per day"))
    for k, n in counts.most_common(40):
        print("   %-38s %7d %9.1f" % (k[:38], n, n / days))
    ends = [e for e in events if e["ev"] == "tile.end"]
    if ends:
        print("   TILE mode: %d uses, median %d steps, median %.1fs, %d%% sized"
              % (len(ends), statistics.median(e.get("steps", 0) for e in ends),
                 statistics.median(e.get("ms", 0) for e in ends) / 1000,
                 100 * sum(1 for e in ends if e.get("grow")) // len(ends)))
    zooms = [e.get("z", 0) for e in events if e["ev"] == "zoom"]
    if zooms:
        print("   zoom: %d gestures, median rests at %d%%" % (len(zooms), statistics.median(zooms)))
    return {k: n / days for k, n in counts.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=LOG)
    ap.add_argument("--days", type=int, help="only the last N days")
    ap.add_argument("--split", help="YYYY-MM-DD: compare per-day rates before and from this date")
    args = ap.parse_args()
    events = load(args.log)
    if args.days:
        since = datetime.date.today() - datetime.timedelta(days=args.days - 1)
        events = [e for e in events if e["day"] >= since]
    if not events:
        print("nothing logged yet in %s" % args.log)
        return
    first, last = min(e["day"] for e in events), max(e["day"] for e in events)
    print("winlist usage, %s to %s  (%s)" % (first, last, args.log))

    print("\n   %-12s %7s %9s %8s %6s" % ("day", "events", "sessions", "minutes", "tiles"))
    for day in sorted({e["day"] for e in events}):
        d = [e for e in events if e["day"] == day]
        print("   %-12s %7d %9d %8d %6d" % (day, len(d), len({e.get("s") for e in d}),
                                           active_minutes(d), sum(1 for e in d if e["ev"] == "tile.start")))

    if not args.split:
        summary(events, "all", (last - first).days + 1)
        return
    cut = datetime.date.fromisoformat(args.split)
    before = [e for e in events if e["day"] < cut]
    after = [e for e in events if e["day"] >= cut]
    b = summary(before, "before %s" % cut, (cut - first).days if before else 1)
    a = summary(after, "from %s" % cut, (last - cut).days + 1 if after else 1)
    print("\n== change in per-day rate (from − before)")
    for k in sorted(set(a) | set(b), key=lambda k: -abs(a.get(k, 0) - b.get(k, 0)))[:25]:
        print("   %-38s %8.1f → %-8.1f %+.1f" % (k[:38], b.get(k, 0), a.get(k, 0), a.get(k, 0) - b.get(k, 0)))


if __name__ == "__main__":
    main()
