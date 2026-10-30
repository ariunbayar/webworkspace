#!/usr/bin/env python3
"""What winlist has been used for, from the log the page keeps.

Run:  python3 winlist/usage_report.py                 # every day there is
      python3 winlist/usage_report.py --days 7        # the last week
      python3 winlist/usage_report.py --split 2026-10-23  # before vs after a date
      python3 winlist/usage_report.py --all           # without dropping bursts

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


# the keys the page itself acts on (app.js PAGE_KEYS); anything else in the log
# is typing that the page used to let through, before #41
PAGE_KEYS = set("a ? : / Escape b t c u o p n y g 1 z m Enter Space h j k l "
                "ArrowUp ArrowDown ArrowLeft ArrowRight PageUp PageDown".split())
TYPED_GAP = 3000    # ms between keys in one run of typing


def base_key(k):
    """A key without its modifiers: 'S-Enter' -> 'Enter'. A lone '-' is a key."""
    while len(k) > 2 and k[1] == "-" and k[0] in "CASs":
        k = k[2:]
    return k


def mask_typing(events):
    """Hide what older logs spelled out. A NORMAL key the page does nothing with
    becomes 'char' (one character) or 'other'. A run of keys, under TYPED_GAP
    apart, that holds such a character was typing, so every character in it is
    masked, the page's letters too. Events are changed in place and keep their
    order; returns how many were masked."""
    n, run = 0, []

    def flush():
        nonlocal n
        typed = any(len(base_key(e["k"])) == 1 and base_key(e["k"]) not in PAGE_KEYS for e in run)
        for e in run:
            b = base_key(e["k"])
            if b in ("char", "other"):
                continue
            if len(b) == 1 and (typed or b not in PAGE_KEYS):
                e["k"] = "char"; n += 1
            elif b not in PAGE_KEYS and b != e["k"] and e["k"].startswith(("C-", "A-")):
                continue          # a page shortcut with a modifier (Ctrl+Space, Ctrl+Alt+F)
            elif b not in PAGE_KEYS and len(b) > 1:
                e["k"] = "other"; n += 1
        run.clear()

    for e in sorted((e for e in events if e.get("ev") == "key" and isinstance(e.get("k"), str)
                     and e.get("mode") == "normal"), key=lambda e: (str(e.get("s")), e["t"])):
        if run and (e.get("s") != run[-1].get("s") or e["t"] - run[-1]["t"] > TYPED_GAP):
            flush()
        run.append(e)
    flush()
    return n


BURST = 300     # of one event in one minute by one page; fast key repeat reaches ~200


def drop_bursts(events):
    """Leave out what one page did over BURST times of one kind in a minute: a
    loop (one page logged 1584 card adds in four minutes), not use. Returns
    what is left, and how many events and pages were left out."""
    per = collections.Counter((e.get("s"), e["ev"], int(e["t"] // 60000)) for e in events)
    bad = {k for k, n in per.items() if n >= BURST}
    kept = [e for e in events if (e.get("s"), e["ev"], int(e["t"] // 60000)) not in bad]
    return kept, len(events) - len(kept), len({k[0] for k in bad})


def name(e):
    """An event as it reads in a table: a key with its mode, an action with its kind."""
    if e["ev"] == "key":
        return "key %s (%s)" % (e.get("k", "?"), e.get("mode", "?"))
    out = e["ev"] if "kind" not in e else "%s %s" % (e["ev"], e["kind"])
    if "by" in e:
        out += " by " + str(e["by"])
    if "why" in e:
        out += " (%s)" % e["why"]
    if e.get("gh"):
        out += " gh"
    return out


def active_minutes(events):
    """Minutes with at least one thing done, per session: time actually spent."""
    return len({(e.get("s"), int(e["t"] // 60000)) for e in events if e["ev"] not in ("close", "page.close")})


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
    for ev, field, what in (("pick", "by", "picks by source"), ("activate", "by", "entries by source"),
                            ("term.close", "why", "terminal closes by cause")):
        by = collections.Counter(e.get(field, "?") for e in events if e["ev"] == ev and field in e)
        if by:
            print("   %s: %s" % (what, ", ".join("%s %d" % kv for kv in by.most_common())))
    # a re-entry is going back into the tile you entered last, in the same page load
    ins = sorted((e for e in events if e["ev"] == "activate" and "n" in e), key=lambda e: (str(e.get("s")), e["t"]))
    again = sum(1 for a, b in zip(ins, ins[1:]) if a.get("s") == b.get("s") and a["n"] == b["n"])
    if len(ins) > 1:
        print("   re-entries: %d of %d entries (%d%%)" % (again, len(ins), 100 * again // len(ins)))
    pans = sum(1 for e in events if e["ev"] == "pan")
    if pans:
        print("   pans: %d, %.1f per active minute" % (pans, pans / max(1, active_minutes(events))))
    return {k: n / days for k, n in counts.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=LOG)
    ap.add_argument("--days", type=int, help="only the last N days")
    ap.add_argument("--split", help="YYYY-MM-DD: compare per-day rates before and from this date")
    ap.add_argument("--all", action="store_true", help="keep bursts (a loop's worth of one event in a minute)")
    args = ap.parse_args()
    events = load(args.log)
    mask_typing(events)
    if not args.all:
        events, n, pages = drop_bursts(events)
        if n:
            print("ignored %d events from %d sessions (bursts of %d+ in a minute; --all keeps them)" % (n, pages, BURST))
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
