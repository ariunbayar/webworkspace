#!/usr/bin/env python3
"""Open windows by workspace — live web dashboard, stdlib only.

Lists every visible window grouped into the workspace grid the desktop actually
uses, and focuses one on click or keyboard pick.

Run:  python3 winlist_server.py           # then open http://localhost:8766
      python3 winlist_server.py --port N  # custom port
      python3 winlist_server.py --open      # and bring the page up in the browser
      python3 winlist_server.py --no-focus  # read-only, refuse focus requests
      python3 winlist_server.py --no-screens  # never photograph the screen

Terminals the page started itself sit on the same surface as the real windows,
drawn by xterm.js rather than photographed. pty_server.py holds them, and this
runs it inside itself: one program to start, one to stop, and no shell left
behind when it stops.

X11 only: it reads EWMH properties via xprop/xdotool, and photographs the
workspace you are on with xwd + ImageMagick's convert.
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WIN_ID = re.compile(r"^0x[0-9a-fA-F]+$")

# ---- shelling out ---------------------------------------------------------


def sh(*args, timeout=5):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def prop(text, name):
    """Value of one property out of a multi-property xprop dump.

    xprop prints either `NAME(TYPE) = value` or, for window lists,
    `NAME(WINDOW): window id # 0xa, 0xb`."""
    m = re.search(r"^%s(?:\([^)]*\))?\s*[=:]\s*(.*)$" % re.escape(name), text, re.M)
    return m.group(1).strip() if m else ""


def unquote(s):
    return s.strip().strip('"')


# ---- workspace grid -------------------------------------------------------


def grid_layout(n):
    """(cols, rows, source) of the workspace grid, laid out row-major.

    GNOME reports a flat list of workspaces and leaves _NET_DESKTOP_LAYOUT
    unset, so the real grid lives in the wsmatrix extension's settings. Fall
    back to the EWMH hint, then to a near-square guess.
    """
    dump = sh("dconf", "dump", "/org/gnome/shell/extensions/wsmatrix/")
    cols = re.search(r"^num-columns=(\d+)", dump, re.M)
    rows = re.search(r"^num-rows=(\d+)", dump, re.M)
    if cols and rows:
        return int(cols.group(1)), int(rows.group(1)), "wsmatrix"

    hint = re.findall(r"\d+", prop(sh("xprop", "-root", "_NET_DESKTOP_LAYOUT"), "_NET_DESKTOP_LAYOUT"))
    if len(hint) >= 3 and int(hint[1]):
        c = int(hint[1])
        return c, int(hint[2]) or -(-n // c), "_NET_DESKTOP_LAYOUT"

    c = max(1, int(n ** 0.5))
    return c, -(-n // c), "guessed"


# ---- which app is this, really --------------------------------------------

# A terminal's WM_CLASS names the terminal, not what you are looking at, so for
# those we walk the process tree and report the program running inside.
TERMINAL_CLASSES = {"xterm", "gnome-terminal-server", "kitty", "alacritty",
                    "konsole", "urxvt", "st", "tilix", "terminator"}
SHELLS = {"bash", "sh", "zsh", "fish", "dash", "tmux", "screen", "su", "sudo", "env"}
PRETTY = {
    "claude": "Claude Code", "vim": "Vim", "nvim": "Neovim", "emacs": "Emacs",
    "ssh": "SSH", "htop": "htop", "top": "top", "btop": "btop", "less": "less",
    "man": "man", "git": "git", "docker": "docker", "npm": "npm", "node": "Node",
    "psql": "psql", "memmon": "memmon", "python3": "Python", "python": "Python",
    "google-chrome": "Google Chrome", "chrome": "Google Chrome", "chromium": "Chromium",
    "firefox": "Firefox", "code": "VS Code", "viber": "Viber", "viberpc": "Viber",
    "nautilus": "Files", "gedit": "Text Editor", "libreoffice": "LibreOffice",
    "thunderbird": "Thunderbird", "slack": "Slack", "spotify": "Spotify",
}
# Anything else running in a terminal is reported as plain "Terminal"; add the
# commands worth naming here.
NAMED_IN_TERMINAL = set(PRETTY) - {"google-chrome", "chrome", "chromium", "firefox",
                                   "code", "viber", "viberpc", "nautilus", "gedit",
                                   "libreoffice", "thunderbird", "slack", "spotify"}

_app_cache = {}  # pid -> (expires_at, app name)
TITLE_SUFFIX = re.compile(r"\s+[-—]\s+(Google Chrome|Chromium|Mozilla Firefox|VIM)$")


def children(pid, depth=4):
    """Breadth-first walk of the process tree under pid -> [(comm, args)]."""
    found, frontier = [], [pid]
    for _ in range(depth):
        nxt = []
        for p in frontier:
            for line in sh("ps", "--ppid", str(p), "-o", "pid=,comm=,args=").splitlines():
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    found.append((parts[1], parts[2] if len(parts) > 2 else ""))
                    nxt.append(parts[0])
        frontier = nxt
        if not frontier:
            break
    return found


def resolve_app(cls, pid, ttl=8):
    cached = _app_cache.get(pid)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    key = cls.lower()
    app = PRETTY.get(key, cls or "Unknown")
    comm = sh("ps", "-p", str(pid), "-o", "comm=").strip() if pid else ""
    # font-cozette & friends: an xterm launched with -class, still a terminal
    if key in TERMINAL_CLASSES or comm in TERMINAL_CLASSES or key.startswith("font-"):
        app = "Terminal"
        for ccomm, cargs in children(pid):
            if ccomm in SHELLS:
                continue
            if ccomm in ("python3", "python"):
                m = re.search(r"([\w.-]+)\.py\b", cargs) or re.search(r"\b(memmon)\b", cargs)
                name = (m.group(1) if m else "python3").removesuffix(".py")
                app = PRETTY.get(name, name)
            elif ccomm in NAMED_IN_TERMINAL:
                app = PRETTY.get(ccomm, ccomm)
            else:
                app = "Terminal"
            break

    _app_cache[pid] = (now + ttl, app)
    return app


# ---- photographing a workspace --------------------------------------------

# X hands out what is actually on the glass: a window sitting on another
# workspace is unmapped, and asking for its pixels returns whatever the root
# happens to be showing in that rectangle. So there is exactly one thing worth
# grabbing — the whole workspace in front of you — and the map fills in cell by
# cell as you move around, each one showing when it was last seen.

SHOTS_ON = True
PTY_PORT = 8767       # pty_server.py, if it is running: terminals of our own
PTY_ON = True
_pty_error = ""
SHOT_WIDTH = 1280     # the virtual screen cuts single windows out of this
SHOT_QUALITY = 72
SHOT_TTL = 2.0        # seconds before the workspace on screen is worth regrabbing
WATCH_FOR = 15.0      # keep grabbing this long after a page last asked for shots
AFTER_FOCUS = 30.0    # ...and this long after a click sent us somewhere new
SWITCH_SETTLE = 0.9   # let a workspace switch land before photographing it

# desktop -> {"data": jpeg, "at": epoch, "clock": "10:07:12", "rects": {id: [x,y,w,h]}}
_shots = {}
_shots_lock = threading.Lock()
_shot_error = ""
_want_until = 0.0     # a page is watching the map until this moment
_hold_until = 0.0


def watch_shots():
    """A page just asked for screens; keep the grabber awake for a while."""
    global _want_until
    _want_until = time.time() + WATCH_FOR


def hold_shots():
    """A click just sent us to another workspace.

    Let the switch land before photographing, then keep grabbing for a while:
    the page is in the background now that the focused window is in front of it,
    so its polls are throttled and cannot ask for the workspace we just landed
    on — which is the one worth having a picture of."""
    global _hold_until, _want_until
    now = time.time()
    _hold_until = now + SWITCH_SETTLE
    _want_until = max(_want_until, now + AFTER_FOCUS)


def grab():
    """The visible screen as a JPEG, or b"" with the reason left in _shot_error."""
    global _shot_error
    if not shutil.which("convert"):
        _shot_error = "ImageMagick's convert is not installed"
        return b""
    try:
        raw = subprocess.run(["xwd", "-root", "-silent"], capture_output=True, timeout=5)
        jpg = subprocess.run(["convert", "xwd:-", "-resize", "%dx" % SHOT_WIDTH,
                              "-quality", str(SHOT_QUALITY), "jpg:-"],
                             input=raw.stdout, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        _shot_error = "capture failed (%s)" % e.__class__.__name__
        return b""
    if not jpg.stdout:
        _shot_error = jpg.stderr.decode("utf-8", "replace")[:120].strip() or "capture came back empty"
        return b""
    _shot_error = ""
    return jpg.stdout


def keep_shots():
    """Photograph the workspace in front of us while a page is watching."""
    while True:
        time.sleep(0.5)
        now = time.time()
        if now > _want_until or now < _hold_until:
            continue
        try:
            desktop = int(prop(sh("xprop", "-root", "_NET_CURRENT_DESKTOP"), "_NET_CURRENT_DESKTOP"))
        except ValueError:
            continue
        with _shots_lock:
            have = _shots.get(desktop)
        if have and now - have["at"] < SHOT_TTL:
            continue
        data = grab()
        if not data:
            time.sleep(5)  # a capture that cannot work is not worth retrying twice a second
            continue
        # right after the shutter, so the rectangles match what is in the photo
        ids = re.findall(r"0x[0-9a-f]+", prop(sh("xprop", "-root", "_NET_CLIENT_LIST"),
                                              "_NET_CLIENT_LIST"))
        rects = {wid: [g.get("x", 0), g.get("y", 0), g.get("width", 0), g.get("height", 0)]
                 for wid, g in geometries(ids).items()}
        order = re.findall(r"0x[0-9a-f]+", prop(sh("xprop", "-root", "_NET_CLIENT_LIST_STACKING"),
                                                "_NET_CLIENT_LIST_STACKING"))
        with _shots_lock:
            _shots[desktop] = {"data": data, "at": time.time(), "clock": time.strftime("%H:%M:%S"),
                               "rects": rects, "order": order}


def shot_index():
    """What the page needs to know: which cells have a photo, and how old."""
    now = time.time()
    with _shots_lock:
        return {str(d): {"clock": s["clock"], "age": round(now - s["at"], 1)}
                for d, s in _shots.items()}


def shot_bytes(desktop):
    with _shots_lock:
        s = _shots.get(desktop)
    return s["data"] if s else b""


# ---- sampling -------------------------------------------------------------


def pty(path, method="GET", body=None, timeout=0.3):
    """Ask the terminal server something, and take no for an answer.

    It is a separate program on a separate port and may simply not be running,
    which is not an error — the surface is still a surface without it. So a
    short timeout, and None means "no terminals today".
    """
    global _pty_error
    url = "http://127.0.0.1:%d%s" % (PTY_PORT, path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _pty_error = ""
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except ValueError:
            _pty_error = "pty_server said %d" % e.code
            return None
    except (OSError, ValueError):
        _pty_error = "pty_server is not answering on :%d" % PTY_PORT
        return None


# A terminal has no rectangle on any screen, so it needs a size to start with.
# The page measures the real one as soon as xterm.js has laid a session out and
# says so; until then this is only enough to put a tile somewhere sensible.
CELL_W, CELL_H, CAPTION, GAP = 9, 17, 22, 60


def terminals(desktop, across):
    """Sessions from pty_server.py, shaped like windows so they can share the
    surface. They belong to no workspace — the desktop has never heard of them
    — so they are given a cell of their own, past the last real one.

    A window arrives with somewhere to be; a terminal does not, and two of them
    at the same nowhere would sit exactly on top of each other. So they are
    laid out left to right and wrapped at about the width of a screen, which is
    only where they start: drag one and it stays where you put it.
    """
    answer = pty("/sessions") if PTY_ON else None
    if not answer:
        return []
    out, x, y, tall = [], 0, 0, 0
    for i, t in enumerate(answer.get("sessions", [])):
        name = t.get("title") or t.get("running") or "shell"
        where = t.get("cwd") or ""
        wide = t.get("cols", 80) * CELL_W
        high = t.get("rows", 24) * CELL_H + CAPTION
        if x and x + wide > across:
            x, y, tall = 0, y + tall + GAP, 0
        tall = max(tall, high)
        out.append({
            "id": "web:" + t["id"],
            "title": name if not where else "%s — %s" % (name, where),
            "app": "Terminal",
            "cls": "pty",
            "pid": t.get("pid", 0),
            "desktop": desktop,
            "focused": False,
            "max": False,
            "min": False,
            "x": x, "y": y,
            "w": wide, "h": high,
            "z": 10000 + i,          # ours, so always above the photographs
            "crop": None, "over": [], "seen": 1.0,
            # everything the page needs to draw one and talk to it
            "term": {
                "session": t["id"],
                "cols": t.get("cols", 80), "rows": t.get("rows", 24),
                "alive": t.get("alive", False), "exit": t.get("exit"),
                "running": t.get("running", ""), "cwd": where,
                "age": t.get("age", 0),
            },
        })
        x += wide + GAP
    return out


def start_terminals(port):
    """Run the terminal server inside this one.

    It is its own program and still runs as one, but there is no reason to make
    somebody start two things and remember to stop two things — and a shell
    left running after the page that opened it has gone is exactly what a
    terminal is supposed to prevent. So it is held here, on threads of this
    process, and it goes when this goes.

    Somebody already listening on that port is a pty_server started by hand:
    that one is theirs to own and to stop, so we leave it alone and use it.
    """
    global _pty_error
    try:
        import pty_server
    except ImportError as e:
        _pty_error = "no terminal server here to run (%s)" % e
        return None
    try:
        return pty_server.serve(port=port)
    except OSError:
        return None            # somebody else's, already there


def stop_terminals(srv):
    if srv:
        import pty_server
        pty_server.stop(srv)


def geometries(ids):
    """{window id: {x, y, width, height}} for the lot, in one xdotool call."""
    chain = []
    for wid in ids:
        chain += ["getwindowgeometry", "--shell", wid]
    geoms, cur = {}, {}
    for line in sh("xdotool", *chain).splitlines() if chain else []:
        k, _, v = line.partition("=")
        if k == "WINDOW":
            cur = geoms.setdefault("0x%x" % int(v), {})
        elif k in ("X", "Y", "WIDTH", "HEIGHT") and cur is not None:
            cur[k.lower()] = int(v)
    return geoms


def union_area(rects):
    """Area covered by a pile of rectangles, counting overlaps once."""
    xs = sorted({v for r in rects for v in (r[0], r[0] + r[2])})
    ys = sorted({v for r in rects for v in (r[1], r[1] + r[3])})
    total = 0
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            x, y, w, h = xs[i], ys[j], xs[i + 1] - xs[i], ys[j + 1] - ys[j]
            if any(r[0] <= x and x + w <= r[0] + r[2]
                   and r[1] <= y and y + h <= r[1] + r[3] for r in rects):
                total += w * h
    return total


def mark_covered(windows, stacks):
    """Which parts of each window's crop are not that window at all.

    The photo is of a whole workspace, so cutting a window's rectangle out of it
    also cuts out whatever was lying on top. The stacking order at the shutter
    says exactly which parts those are: hand them to the page as percentages of
    the crop, along with how much of the window was left showing, and it can
    grey out everything that is somebody else.
    """
    per_desktop = {}
    for w in windows:
        if w["crop"]:
            per_desktop.setdefault(w["desktop"], []).append(w)

    for desktop, group in per_desktop.items():
        rank = {wid: i for i, wid in enumerate(stacks.get(desktop, []))}
        for w in group:
            x, y, ww, hh = w["crop"]
            if ww <= 0 or hh <= 0:
                continue
            mine = rank.get(w["id"], -1)
            hidden = []
            for v in group:
                if v is w or rank.get(v["id"], -1) <= mine:
                    continue          # below us, or the same window: not in the way
                vx, vy, vw, vh = v["crop"]
                ax, ay = max(x, vx), max(y, vy)
                bx, by = min(x + ww, vx + vw), min(y + hh, vy + vh)
                if bx > ax and by > ay:
                    hidden.append([ax - x, ay - y, bx - ax, by - ay])
            w["over"] = [[round(r[0] * 100.0 / ww, 2), round(r[1] * 100.0 / hh, 2),
                          round(r[2] * 100.0 / ww, 2), round(r[3] * 100.0 / hh, 2)]
                         for r in hidden]
            w["seen"] = round(1 - union_area(hidden) / float(ww * hh), 3) if hidden else 1.0


def sample():
    roots = sh("xprop", "-root", "_NET_CLIENT_LIST", "_NET_CLIENT_LIST_STACKING",
               "_NET_NUMBER_OF_DESKTOPS", "_NET_CURRENT_DESKTOP", "_NET_DESKTOP_GEOMETRY")
    if not roots:
        return {"error": "no X11 window manager reachable (is DISPLAY set?)", "windows": []}

    ids = re.findall(r"0x[0-9a-f]+", prop(roots, "_NET_CLIENT_LIST"))
    stacking = re.findall(r"0x[0-9a-f]+", prop(roots, "_NET_CLIENT_LIST_STACKING"))
    order = {wid: i for i, wid in enumerate(stacking)}  # bottom -> top

    n_desktops = int(prop(roots, "_NET_NUMBER_OF_DESKTOPS") or 1)
    current = int(prop(roots, "_NET_CURRENT_DESKTOP") or 0)
    geom = [int(x) for x in re.findall(r"\d+", prop(roots, "_NET_DESKTOP_GEOMETRY"))] or [1920, 1080]
    names = re.findall(r'"((?:[^"\\]|\\.)*)"', sh("xprop", "-root", "_NET_DESKTOP_NAMES"))
    cols, rows, grid_src = grid_layout(n_desktops)

    geoms = geometries(ids)
    with _shots_lock:                       # where each window sat, and who was on
        crops = {d: s["rects"] for d, s in _shots.items()}          # top of whom, when
        stacks = {d: s.get("order", []) for d, s in _shots.items()}  # it was photographed

    windows = []
    for wid in ids:
        p = sh("xprop", "-id", wid, "_NET_WM_NAME", "WM_NAME", "WM_CLASS",
               "_NET_WM_PID", "_NET_WM_DESKTOP", "_NET_WM_STATE")
        state = prop(p, "_NET_WM_STATE")
        if "SKIP_TASKBAR" in state or "SKIP_PAGER" in state:
            continue  # panels, OSDs, shell overlays
        title = unquote(prop(p, "_NET_WM_NAME") or prop(p, "WM_NAME"))
        if not title or "not found" in title:
            continue
        try:
            desktop = int(prop(p, "_NET_WM_DESKTOP"))
        except ValueError:
            continue
        if desktop < 0 or desktop >= n_desktops:
            continue  # sticky / on no workspace
        try:
            pid = int(prop(p, "_NET_WM_PID"))
        except ValueError:
            pid = 0
        cls = unquote(prop(p, "WM_CLASS").split(",")[-1])
        g = geoms.get(wid, {})
        windows.append({
            "id": wid,
            "title": TITLE_SUFFIX.sub("", title).strip(),
            "app": resolve_app(cls, pid),
            "cls": cls,
            "pid": pid,
            "desktop": desktop,
            "focused": "FOCUSED" in state,
            "max": "MAXIMIZED_VERT" in state,
            "min": "HIDDEN" in state,
            "x": g.get("x", 0), "y": g.get("y", 0),
            "w": g.get("width", 0), "h": g.get("height", 0),
            "z": order.get(wid, 0),
            # where to cut this window out of its workspace photo, which is not
            # quite where it is now if it has been moved since
            "crop": crops.get(desktop, {}).get(wid),
            "over": [],        # the parts of that crop that are somebody else
            "seen": 1.0,       # ...and how much of it is really this window
        })

    mark_covered(windows, stacks)
    windows += terminals(n_desktops, geom[0])
    windows.sort(key=lambda w: (w["desktop"], -w["z"]))  # topmost first within a workspace
    return {
        "captured": time.strftime("%H:%M:%S"),
        "desktops": n_desktops,
        "current": current,
        "names": names[:n_desktops],
        "grid": {"cols": cols, "rows": rows, "source": grid_src},
        "screen": {"w": geom[0], "h": geom[1]},
        "windows": windows,
        "shots": shot_index(),
        "shots_on": SHOTS_ON,
        "shot_error": _shot_error,
        # where the page dials for a terminal, and which cell they live in
        "pty": {"on": PTY_ON, "port": PTY_PORT, "cell": n_desktops, "error": _pty_error},
    }


def focus(wid):
    """Raise a window and switch to its workspace."""
    if wid.startswith("web:"):
        return False, "that terminal lives in the page, not on the desktop"
    if not WIN_ID.match(wid):
        return False, "bad window id"
    if wid.lower() not in [w.lower() for w in
                           re.findall(r"0x[0-9a-f]+", sh("xprop", "-root", "_NET_CLIENT_LIST"))]:
        return False, "no such window"
    sh("xdotool", "windowactivate", wid)
    return True, "ok"


BROWSERS = {"Google Chrome", "Chromium", "Firefox"}
PAGE_TITLE = "Open windows"
DEFAULT_PORT = 8766


def page_title(port):
    """Off the default port the title carries it, so one winlist's page is
    never mistaken for another's."""
    return PAGE_TITLE if port == DEFAULT_PORT else "%s :%d" % (PAGE_TITLE, port)


def find_page_window(title):
    """The browser window showing our page, if one is up."""
    pattern = "^%s( [-—] .*)?$" % re.escape(title)   # browsers append their own name
    for num in re.findall(r"\d+", sh("xdotool", "search", "--name", pattern)):
        wid = "0x%x" % int(num)
        cls = unquote(sh("xprop", "-id", wid, "WM_CLASS").split(",")[-1])
        if PRETTY.get(cls.lower()) in BROWSERS:
            return wid
    return None


def show_page(url, port):
    """Bring the page up, reusing a browser window already showing it.

    Plain xdg-open adds a tab on every launch, and leaves it in whichever
    window the browser picked — which may be on another workspace entirely.
    So look for the page first, and raise whatever we end up with."""
    want = page_title(port)
    wid = find_page_window(want)
    if wid:
        sh("xdotool", "windowactivate", wid)
        return "raised the window already showing it"
    sh("xdg-open", url)
    for _ in range(12):
        time.sleep(0.25)
        wid = find_page_window(want)
        if wid:
            sh("xdotool", "windowactivate", wid)
            break
    return "opened it in the browser"


# ---- page -----------------------------------------------------------------

PAGE = r"""<!doctype html>
<meta charset="utf-8">
<title>__TITLE__</title>
<link rel="stylesheet" href="/vendor/xterm.css">
<script src="/vendor/xterm.js"></script>
<style>
  :root { --bg:#f7f7f5; --panel:#fff; --line:#e3e2dd; --fg:#1c1b19; --dim:#6f6d67;
          --accent:#b8562f; --chip:#efeee9; --empty:#f2f1ed }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#15140f; --panel:#1d1c17; --line:#2f2d26; --fg:#e9e7df; --dim:#918e84;
            --accent:#e0875c; --chip:#26241d; --empty:#191811 }
  }
  * { box-sizing:border-box }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:13px/1.4 ui-sans-serif,system-ui,"Ubuntu",sans-serif }
  .wrap { max-width:1180px; margin:0 auto; padding:20px 18px 46px }
  h1 { font-size:18px; margin:0 0 2px; font-weight:600 }
  .sub { color:var(--dim); font-size:12px; margin-bottom:12px }
  .sub b { color:var(--fg); font-weight:600 }
  .stale { color:var(--accent) }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:14px }
  input[type=search] { flex:1 1 200px; max-width:300px; padding:6px 9px; font:inherit;
    border:1px solid var(--line); border-radius:6px; background:var(--panel); color:var(--fg) }
  .keys { margin-left:auto; color:var(--dim); font-size:11px }

  /* the whole browser window, without going properly fullscreen: the page just
     stops being a column of content and becomes the app */
  body.full .wrap { max-width:none; padding:10px 12px 16px }
  body.full h1, body.full footer, body.full .keys { display:none }
  body.full .sub { margin-bottom:8px }
  body.full .bar { margin-bottom:10px }
  /* the surface wants the viewport itself rather than a column of page */
  body.app { overflow:hidden }
  body.app .wrap { height:100vh; padding-bottom:10px; display:flex; flex-direction:column }
  body.app .pan { flex:1; min-height:0; height:auto }
  kbd { font:11px ui-monospace,monospace; border:1px solid var(--line); border-bottom-width:2px;
        border-radius:3px; padding:0 4px; background:var(--panel) }

  .dot { width:7px; height:7px; border-radius:2px; flex:none }
  .t2 { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px }

  /* the virtual screen: every window on one surface, arranged however you like */
  .ctl { display:flex; gap:8px; align-items:center }
  .btn { border:1px solid var(--line); background:var(--panel); color:var(--dim); font:inherit;
         font-size:12px; padding:5px 10px; border-radius:6px; cursor:pointer }
  .btn:hover { color:var(--fg); border-color:var(--dim) }
  .btn[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:#fff }
  #full { font-size:14px; line-height:1; padding:5px 9px }
  #zoom { width:96px; accent-color:var(--accent) }
  /* the surface is placed, not scrolled: overflow is hidden and the canvas is
     translated, so a drag can carry everything as far as you like */
  .pan { position:relative; overflow:hidden; border:1px solid var(--line);
         border-radius:8px; background:var(--empty); height:min(78vh,900px); min-height:380px;
         touch-action:none; user-select:none; -webkit-user-select:none; cursor:grab }
  .pan.grabbing { cursor:grabbing }
  .canvas { position:absolute; top:0; left:0; width:0; height:0; will-change:transform }
  .tile { position:absolute; border-radius:5px; overflow:hidden; background:var(--panel);
          border:1px solid var(--line); box-shadow:0 2px 8px rgba(0,0,0,.16);
          display:flex; flex-direction:column; cursor:grab; touch-action:none }
  .tile:hover { border-color:var(--dim) }
  .tile.dragging { cursor:grabbing; box-shadow:0 12px 34px rgba(0,0,0,.4); z-index:60 }
  .tile.focused { border-color:var(--accent) }
  .tile.sel { outline:2px solid var(--accent); outline-offset:1px }
  .tile.off { opacity:.3 }
  .cap { display:flex; align-items:center; gap:5px; padding:3px 6px; flex:none;
         border-bottom:1px solid var(--line); background:var(--panel) }
  .cap .t2 { font-size:11px }
  .pic { position:relative; flex:1; min-height:0; background-repeat:no-repeat;
         background-origin:border-box }
  .pic.none { display:flex; align-items:center; justify-content:center; color:#fff;
              font-size:10px; text-shadow:0 1px 2px rgba(0,0,0,.4); text-align:center;
              padding:0 6px }
  /* A terminal is not a photograph of anything — it is the session itself,
     live. So the whole tile is drawn at the size the terminal really wants and
     then scaled with the rest of the surface: zoom out and it goes small like
     everything else, zoom in and you can read it and type into it. */
  .tile.term { background:#12110d; border-color:#3a372c }
  .tile.term.focused { border-color:var(--accent) }
  .termwrap { position:absolute; top:0; left:0; transform-origin:0 0;
              display:flex; flex-direction:column }
  .termwrap .cap { background:#1d1c17; border-bottom-color:#34322a; color:#b9b5a8;
                   cursor:grab; flex:none }
  .tile.term.dragging .termwrap .cap { cursor:grabbing }
  .termhost { flex:none }
  .termhost .xterm { padding:2px 3px }
  /* a session that has ended keeps its last words, and says so */
  .tile.gone { opacity:.62 }
  .cap .shut { flex:none; cursor:pointer; opacity:.55; padding:0 3px; font-size:12px;
               line-height:1; border-radius:3px }
  .cap .shut:hover { opacity:1; background:var(--accent); color:#fff }
  .cap .note { flex:none; font-size:10px; opacity:.75 }
  /* a corner to pull: the terminal is the only tile with a size of its own to
     change, since the rest are pictures of windows somebody else is sizing */
  .grip { position:absolute; right:0; bottom:0; width:14px; height:14px;
          cursor:nwse-resize; opacity:.45;
          background:linear-gradient(135deg, transparent 45%, #b9b5a8 45% 55%,
                     transparent 55% 70%, #b9b5a8 70% 80%, transparent 80%) }
  .grip:hover { opacity:.95 }
  .tile.gone .grip { display:none }
  .termsize { position:absolute; right:6px; bottom:6px; padding:1px 5px; border-radius:3px;
              background:rgba(0,0,0,.72); color:#e9e7df; font:11px ui-monospace,monospace;
              pointer-events:none }

  /* a photo of a workspace shows whatever was on top, so the parts of this
     window that something else was covering get struck out rather than passed
     off as its own content */
  .hid { position:absolute; background:var(--empty);
         background-image:repeating-linear-gradient(45deg,
           rgba(128,128,128,.22) 0 4px, transparent 4px 9px) }
  /* what the whole thing is, on demand: a picture of the pieces and who
     talks to whom, since none of it is visible from the page itself */
  dialog { border:1px solid var(--line); border-radius:10px; background:var(--panel);
           color:var(--fg); padding:0; max-width:min(96vw,940px) }
  dialog::backdrop { background:rgba(0,0,0,.45) }
  .archhead { display:flex; align-items:center; gap:10px; padding:9px 13px;
              border-bottom:1px solid var(--line) }
  .archhead h2 { font-size:13px; margin:0; font-weight:600 }
  .grow { flex:1 }
  .archbody { padding:12px 13px 15px; overflow:auto; max-height:min(74vh,780px) }
  /* box drawing only joins up in a font whose glyphs span the whole cell, and
     only at a line height of exactly one line — anything looser leaves gaps */
  .archbody pre { margin:0; white-space:pre; font-size:11.5px; line-height:1;
                  font-family:"DejaVu Sans Mono","Liberation Mono","Noto Sans Mono",monospace }
  .archbody p { color:var(--dim); font-size:11px; margin:11px 0 0; max-width:64ch }
  .archbody b { color:var(--fg); font-weight:600 }
  footer { color:var(--dim); font-size:11px; margin-top:18px; border-top:1px solid var(--line); padding-top:9px }
  code { font-size:10.5px; background:var(--chip); padding:1px 4px; border-radius:3px }
</style>
<div class="wrap">
  <h1>Open windows</h1>
  <div class="sub"><b id="stat">loading…</b> · <span id="ts"></span></div>
  <div class="bar">
    <input type="search" id="q" placeholder="Filter title or app…">
    <button id="full" class="btn" aria-pressed="false"
            title="Give it the whole browser window (f)">⤢</button>
    <span class="ctl" id="ctl">
      <input type="range" id="zoom" min="2" max="100" step="1" title="Zoom">
      <button id="fit" class="btn">Fit</button>
      <button id="reset" class="btn">Reset layout</button>
      <button id="newterm" class="btn" title="Start a terminal on this surface (t)">New terminal</button>
      <button id="arch" class="btn" title="How this fits together (a)">Architecture</button>
    </span>
    <span class="keys"><kbd>↑↓←→</kbd>/<kbd>hjkl</kbd> pick · <kbd>Enter</kbd> focus ·
      <kbd>/</kbd> filter · <kbd>f</kbd> full window · <kbd>t</kbd> terminal ·
      <kbd>a</kbd> architecture · <kbd>Esc</kbd> clear</span>
  </div>
  <div class="pan" id="pan"><div class="canvas" id="canvas"><div id="tiles"></div></div></div>
  <footer id="foot"></footer>
</div>
<dialog id="archbox">
  <div class="archhead">
    <h2>How this fits together</h2><span class="grow"></span>
    <button id="archclose" class="btn">Close</button>
  </div>
  <div class="archbody">
<pre>  ┌──────────────────────── Chrome ────────────────────────┐
  │  the virtual screen — this page                        │
  │                                                        │
  │   ┌─────────┐ ┌─────────┐    ┌──────────────────────┐  │
  │   │ window  │ │ window  │    │ tile: xterm.js       │  │
  │   │  photo  │ │  photo  │    │ $ npx tsc --noEmit▌  │  │
  │   └─────────┘ └─────────┘    └────▲────────────┬────┘  │
  │      tiles you arrange by hand    │            │       │
  └───────────────────────────────────┼────────────┼───────┘
        ▲                             │ bytes out  │ keys in
        │ GET /api/windows            │ WebSocket  │
        │                             │            │
  ┌─────┴──────────────┐         ┌────┴────────────▼─────┐
  │ winlist_server.py  │   GET   │ pty_server.py         │
  │      :_PORT_       │────────►│      :8767            │
  │ xprop · xdotool    │/sessions│ pty.fork + select     │
  │ xwd · convert      │  200ms  │ scrollback per shell  │
  └─────┬──────────────┘ timeout └───┬────────────┬──────┘
        │ asks X                     │ PTY        │ PTY
        ▼                            ▼            ▼
  ┌────────────────────┐         ┌──────┐    ┌────────┐
  │ X11 / window mgr   │         │ bash │    │ claude │
  │ Chrome, editors,   │         └──────┘    └────────┘
  │ gnome-terminal     │         shells this page started:
  └────────────────────┘         it owns these, and only these
    watched, never owned</pre>
    <p><b>Left, and running now:</b> real X windows, watched but never owned. The page asks
    <code>xprop</code> and <code>xdotool</code> what exists, and photographs a workspace
    whenever you visit it — X only hands out the pixels on the glass, so a workspace you
    are not looking at cannot be captured.</p>
    <p><b>Right:</b> shells this page starts itself. <code>pty_server.py</code> holds
    them, so it knows their pid, working directory and what is running in them outright
    rather than guessing from <code>WM_CLASS</code>, and they survive a reload — the tab
    only holds the emulator drawing one. Sessions arrive in the same
    <code>windows[]</code> list as synthetic entries, in a cell of their own past the
    last workspace, which is what lets them share the surface with real windows.</p>
  </div>
</dialog>
<script>
const COLORS = { "Google Chrome":"#4285f4", "Claude Code":"#c96442", "Vim":"#019833",
  "Neovim":"#019833", "Viber":"#7360f2", "Firefox":"#ff7139", "memmon":"#7a5cd6",
  "Terminal":"#5a5852", "VS Code":"#0078d4", "Files":"#77767b", "Slack":"#4a154b" };
const PALETTE = ["#2f7d8c","#a8642b","#7a5cd6","#3f7d3f","#94566f","#736b5e"];
const colorOf = a => COLORS[a] || (COLORS[a] = PALETTE[Object.keys(COLORS).length % PALETTE.length]);
const $ = s => document.querySelector(s);
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

// The arrangement lives here, not on the desktop: dragging a window on the
// virtual screen moves the tile and nothing else. Kept per window id, so a
// window we have not seen before falls back to where it really is.
const store = {
  get(k, fb) { try { return JSON.parse(localStorage.getItem('winlist.' + k)) ?? fb; }
               catch (e) { return fb; } },
  set(k, v) { try { localStorage.setItem('winlist.' + k, JSON.stringify(v)); } catch (e) {} },
};

let data = null, failures = 0, sel = null;
let full = store.get('full', false);       // fill the browser window, F11 not involved
let layout = store.get('layout', {});      // window id -> [x, y] on the virtual screen
let zoom = store.get('zoom', 0);           // 0 until we have measured a fit
let origin = store.get('origin', [0, 0]);  // where the surface sits in the frame
let fitting = store.get('fitting', true);  // keep fitting until you take the wheel
const GUTTER = 140;                        // virtual px between one workspace and the next

function shotUrl(i) {
  const s = data.shots && data.shots[i];
  return s ? `/api/screen/${i}?v=${encodeURIComponent(s.clock)}` : null;
}


function setFull(v) {
  full = v;
  store.set('full', v);
  document.body.classList.toggle('full', v);
  document.body.classList.toggle('app', v);
  $('#full').setAttribute('aria-pressed', v);
  render();
}
$('#full').onclick = () => setFull(!full);

// none of the plumbing shows on the page, so it gets a picture of its own
const archbox = $('#archbox');
const showArch = () => { if (!archbox.open) archbox.showModal(); };
$('#arch').onclick = showArch;
$('#archclose').onclick = () => archbox.close();
// squared, so the slider gives fine control down at the small end where the
// whole surface lives and still reaches far enough in to read a window
$('#zoom').addEventListener('input', () => {
  setZoom(MAX_ZOOM * Math.pow($('#zoom').value / 100, 2));
});
$('#fit').onclick = () => { hold(true); fitAll(); render(); };
$('#reset').onclick = () => {
  layout = {};
  store.set('layout', layout);
  hold(true);
  render();
};
// the canvas keeps fitting the window — through a resize, through going
// full-window — until you either work the slider or start arranging tiles
addEventListener('resize', render);
$('#q').addEventListener('input', () => { sel = null; render(); });

async function poll() {
  try {
    // asking for screens is what keeps the grabber awake
    const r = await fetch('/api/windows?screens=1');
    data = await r.json();
    failures = 0;
  } catch (e) { failures++; }
  render();
}

function visible() {
  const q = $('#q').value.trim().toLowerCase();
  return w => !q || (w.title + " " + w.app).toLowerCase().includes(q);
}

function onWorkspace(i) { return data.windows.filter(w => w.desktop === i); }

// Windows of one app sit together, apps ordered by their topmost window, so two
// windows sharing a title never end up split by something stacked between them.
function byApp(ws) {
  const order = [], groups = new Map();
  ws.forEach(w => {
    if (!groups.has(w.app)) { groups.set(w.app, []); order.push(w.app); }
    groups.get(w.app).push(w);
  });
  return order.map(app => [app, groups.get(app)]);
}

// the on-screen order, which is what the arrow keys walk
function ordered(i) { return byApp(onWorkspace(i)).flatMap(([, group]) => group); }

function render() {
  if (!data) return;
  const match = visible(), q = $('#q').value.trim();
  renderCanvas(match, q);
  status(match, q);
}

function status(match, q) {
  const hits = data.windows.filter(match);
  const ours = data.windows.filter(w => w.term).length;
  const desks = new Set(data.windows.filter(w => !w.term).map(w => w.desktop)).size;
  $('#stat').textContent = `${hits.length - ours}${q ? " of " + (data.windows.length - ours) : ""} windows · `
    + (ours ? `${ours} terminal${ours > 1 ? 's' : ''} of our own · ` : '')
    + `${data.grid.cols}×${data.grid.rows} workspaces · ${desks} in use`;
  $('#ts').innerHTML = failures ? `<span class="stale">disconnected — retrying</span>`
    : `updated ${data.captured}`;
  $('#foot').innerHTML = `Every window on one surface, seeded from where it `
      + `really sits and then yours to arrange: drag a tile and only the tile moves — the `
      + `desktop is never touched. The arrangement is remembered in this browser; `
      + `<b>Reset layout</b> puts everything back where the desktop has it. Scroll or `
      + `pinch to zoom, drag the background or slide two fingers to pan, and click a window `
      + `(or press <kbd>Enter</kbd>) to focus it for real. Windows start out grouped by `
      + `the workspace they live on, packed together rather than spread over the desktop's `
      + `own grid.`
    + (!data.shots_on
        ? ` Screens are off (<code>--no-screens</code>), so tiles stay plain colours.`
        : data.shot_error
        ? ` No photographs: ${esc(data.shot_error)}.`
        : ` X can only photograph the workspace in front of you, so a tile shows the last `
          + `look at its workspace; visit one to fill its windows in.`)
    + (!data.pty || !data.pty.on ? ''
       : data.pty.error
       ? ` No terminals: ${esc(data.pty.error)}. Start it with <code>python3 pty_server.py</code>.`
       : ` <b>New terminal</b> starts a shell of this page's own, off to the right of the `
         + `workspaces — drag it by its title bar, click into it and type. It lives in `
         + `<code>pty_server.py</code>, not in this tab, so a reload picks it back up.`);
}


// ---- the virtual screen ----------------------------------------------------
// One surface holding every window there is, and it goes on forever: the
// surface is drawn at an offset and a scale of our choosing rather than scrolled
// inside a box, so a drag can carry everything anywhere and the zoom has no
// stops. A tile starts life where its window really sits and from then on you
// put it wherever you like. Nothing here talks to the window manager: dragging
// rearranges the picture, not the desktop.

const tileEls = new Map();   // window id -> element, kept so a drag survives a poll
const MIN_ZOOM = 0.02, MAX_ZOOM = 4;

// Where a window starts out. The desktop's own 3x6 grid is no use here: it is
// far taller than any browser window and most of its cells are empty, so the
// workspaces that actually hold something get packed into a squarish block
// instead. Windows that shared a workspace still start out together.
let seating = { key: '', cols: 1, at: new Map() };
function plan() {
  const used = [...new Set(data.windows.map(w => w.desktop))].sort((a, b) => a - b);
  const key = used.join(',');
  if (key !== seating.key) {
    seating = { key, cols: Math.max(1, Math.ceil(Math.sqrt(used.length))),
                at: new Map(used.map((d, i) => [d, i])) };
  }
  return seating;
}

function seat(w) {
  const p = plan(), i = p.at.get(w.desktop) || 0;
  const col = i % p.cols, row = Math.floor(i / p.cols);
  return [col * (data.screen.w + GUTTER) + Math.max(0, w.x),
          row * (data.screen.h + GUTTER) + Math.max(0, w.y)];
}
const seatOf = w => layout[w.id] || seat(w);

// what the windows actually cover, which is the thing worth fitting
function bounds() {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  data.windows.forEach(w => {
    const [x, y] = seatOf(w);
    x0 = Math.min(x0, x); y0 = Math.min(y0, y);
    x1 = Math.max(x1, x + Math.max(240, w.w)); y1 = Math.max(y1, y + Math.max(160, w.h));
  });
  return isFinite(x0) ? [x0, y0, x1, y1] : [0, 0, 1, 1];
}

function hold(auto) {
  fitting = auto;
  store.set('fitting', auto);
}

const clamp = z => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

function shift(dx, dy) {          // slide the whole surface, no edges to run into
  origin = [origin[0] + dx, origin[1] + dy];
  store.set('origin', origin);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;
}

// zoom about a point: whatever is under the mouse, or between the fingers, is
// the one thing that must not move
function zoomAbout(next, cx, cy) {
  next = clamp(next);
  if (next === zoom) return;
  const box = $('#pan').getBoundingClientRect();
  const fx = cx - box.left, fy = cy - box.top;
  origin = [fx - (fx - origin[0]) / zoom * next, fy - (fy - origin[1]) / zoom * next];
  zoom = next;
  store.set('zoom', zoom);
  store.set('origin', origin);
  hold(false);
  render();
}

function setZoom(z) {
  const box = $('#pan').getBoundingClientRect();
  zoomAbout(z, box.left + box.width / 2, box.top + box.height / 2);   // about the middle
}

function fitAll() {
  const pan = $('#pan'), [x0, y0, x1, y1] = bounds();
  const pad = 24;
  zoom = clamp(Math.min((pan.clientWidth - pad * 2) / (x1 - x0),
                        (pan.clientHeight - pad * 2) / (y1 - y0)));
  origin = [(pan.clientWidth - (x1 - x0) * zoom) / 2 - x0 * zoom,
            (pan.clientHeight - (y1 - y0) * zoom) / 2 - y0 * zoom];
  store.set('zoom', zoom);
  store.set('origin', origin);
}

// cut this window out of its workspace photo — percentages, so the photo's own
// pixel size never comes into it
function dress(pic, w) {
  const S = data.screen, c = w.crop, url = shotUrl(w.desktop);
  const x = c && Math.max(0, c[0]), y = c && Math.max(0, c[1]);
  const cw = c && Math.min(c[2], S.w - x), ch = c && Math.min(c[3], S.h - y);
  // nothing of this window was showing, so there is nothing honest to display
  const buried = w.seen !== undefined && w.seen < 0.08;
  if (!url || !cw || !ch || buried) {
    pic.className = 'pic none';
    pic.style.cssText = `background:${colorOf(w.app)}`;
    pic.textContent = buried ? 'was behind another window'
      : data.shots_on ? 'not photographed yet' : '';
    return;
  }
  pic.className = 'pic';
  pic.textContent = '';
  pic.style.cssText = `background-image:url("${url}");`
    + `background-size:${S.w / cw * 100}% ${S.h / ch * 100}%;`
    + `background-position:${S.w > cw ? x / (S.w - cw) * 100 : 0}% `
    + `${S.h > ch ? y / (S.h - ch) * 100 : 0}%`;
  (w.over || []).forEach(o => {
    const m = document.createElement('div');
    m.className = 'hid';
    m.style.cssText = `left:${o[0]}%;top:${o[1]}%;width:${o[2]}%;height:${o[3]}%`;
    pic.append(m);
  });
}

function place(el, w) {
  const [x, y] = seatOf(w);
  el.style.left = x * zoom + 'px';
  el.style.top = y * zoom + 'px';
  if (w.term) {
    // a terminal is drawn at its own size and scaled to match the surface, so
    // it cannot be given a floor the way a photograph can: the tile is exactly
    // as big as what is inside it
    const t = terms.get(w.term.session);
    el.style.width = w.w * zoom + 'px';
    el.style.height = w.h * zoom + 'px';
    if (t && t.wrap) t.wrap.style.transform = `scale(${zoom})`;
    return;
  }
  el.style.width = Math.max(90, w.w * zoom) + 'px';
  el.style.height = Math.max(60, w.h * zoom) + 'px';
}

function drag(e, w, el) {
  if (e.button) return;
  e.preventDefault();
  const from = seatOf(w), sx = e.clientX, sy = e.clientY;
  let moved = false;
  el.setPointerCapture(e.pointerId);
  const move = ev => {
    const dx = ev.clientX - sx, dy = ev.clientY - sy;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 5) return;   // still a click
    if (!moved) {
      moved = true;
      el.classList.add('dragging');
      $('#tiles').append(el);          // the one you just touched belongs on top
      // moving an element in the document drops its pointer capture, and the
      // drag then only lasts while the pointer happens to stay over the tile —
      // which for a terminal, grabbed by a thin title bar, is no time at all
      try { el.setPointerCapture(ev.pointerId); } catch (err) {}
    }
    layout[w.id] = [Math.round(from[0] + dx / zoom), Math.round(from[1] + dy / zoom)];
    place(el, w);
  };
  const done = settle => {
    el.removeEventListener('pointermove', move);
    el.removeEventListener('pointerup', up);
    el.removeEventListener('pointercancel', up);
    el.classList.remove('dragging');
    letGo = null;
    // a tile the pinch interrupted keeps the ground it covered, so what is on
    // screen and what is remembered never disagree
    if (moved) { store.set('layout', layout); hold(false); }
    if (!settle) return;
    if (moved) { sel = w.id; render(); } else activate(w.id);
  };
  const up = ev => {
    try { el.releasePointerCapture(ev.pointerId); } catch (err) {}
    done(true);
  };
  letGo = () => done(false);       // dropped where it stands if a pinch begins
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', up);
  el.addEventListener('pointercancel', up);
}

// ---- terminals -----------------------------------------------------------
// A session lives in pty_server.py; what lives here is the emulator drawing it
// and the socket carrying bytes each way. Both are kept per session and reused
// across renders, so a poll never disturbs what you are typing into.

const terms = new Map();          // session id -> { term, ws, wrap, natural }
const TERM_COLS = 100, TERM_ROWS = 30;
// A prompt is whatever the shell says it is, and plenty of them are drawn out
// of a Nerd Font's private use area — a Powerline arrow in a font that has
// never heard of one is a blank. The browser falls back per glyph, so naming a
// symbol font after the workhorse fills those in without disturbing the
// metrics, which come from the first font only.
const TERM_FONT = '"DejaVu Sans Mono","Liberation Mono","PowerlineSymbols",' +
                  '"Symbols Nerd Font","CozetteVector",ui-monospace,monospace';
const TERM_THEME = { background: '#12110d', foreground: '#e9e7df', cursor: '#e0875c',
  black: '#2a2820', red: '#d76b5a', green: '#7fa84f', yellow: '#d0a33c',
  blue: '#6f9bc4', magenta: '#b07ec0', cyan: '#5fa8a0', white: '#d9d5c8' };

function connect(t, id) {
  if (t.ws || !data.pty || !data.pty.on) return;
  const ws = new WebSocket(`ws://${location.hostname}:${data.pty.port}/attach/${id}`);
  ws.binaryType = 'arraybuffer';
  t.ws = ws;
  ws.onmessage = e => {
    // bytes are the terminal; text is the server talking about it, which the
    // window list already covers
    if (typeof e.data !== 'string') t.term.write(new Uint8Array(e.data));
  };
  ws.onclose = () => { if (t.ws === ws) t.ws = null; };
  ws.onerror = () => { if (t.ws === ws) t.ws = null; };
}

function mount(w) {
  const id = w.term.session;
  let t = terms.get(id);
  if (t) return t;
  const term = new Terminal({
    cols: w.term.cols, rows: w.term.rows, theme: TERM_THEME,
    fontFamily: TERM_FONT,
    fontSize: 13, lineHeight: 1.1, cursorBlink: true, scrollback: 4000,
    convertEol: false, macOptionIsMeta: true,
  });
  t = { term, ws: null, wrap: null, natural: null, cell: null, pad: [0, 0] };
  terms.set(id, t);
  // what you type goes straight down the socket; nothing is echoed locally,
  // because the far end is what decides what a keystroke looks like
  term.onData(d => {
    if (t.ws && t.ws.readyState === 1) t.ws.send(new TextEncoder().encode(d));
  });
  return t;
}

function dressTerm(el, w) {
  const t = mount(w), id = w.term.session;
  if (!t.wrap) {
    el.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'termwrap';
    wrap.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span>` +
                     `<span class="note"></span><span class="shut" title="Close">✕</span></div>`;
    const host = document.createElement('div');
    host.className = 'termhost';
    wrap.append(host);
    el.append(wrap);
    // xterm measures a character by laying one out, so it has to do that at
    // its own size: the surface scale goes on afterwards, never before
    wrap.style.transform = 'none';
    t.term.open(host);
    t.wrap = wrap;
    measure(t);
    const grip = document.createElement('div');
    grip.className = 'grip';
    grip.title = 'Drag to resize this terminal';
    el.append(grip);                  // outside the scaled wrap: a handle you
  }                                   // can still grab when zoomed out
  if (t.natural) { w.w = t.natural[0]; w.h = t.natural[1]; }
  const cap = t.wrap.querySelector('.cap');
  cap.querySelector('.dot').style.background = colorOf(w.app);
  cap.querySelector('.t2').textContent = w.term.running || w.title;
  cap.querySelector('.note').textContent = w.term.alive
    ? (w.term.cwd || '') : 'exited ' + (w.term.exit === null ? '?' : w.term.exit);
  el.classList.toggle('gone', !w.term.alive);
  if (w.term.alive) connect(t, id);
}

// What one character costs, worked out from what xterm.js actually laid out
// rather than from anything we told it: the font decides, and it is the only
// one that knows. Everything about a terminal's size follows from this.
function measure(t) {
  const host = t.wrap.querySelector('.termhost');
  const screen = host.querySelector('.xterm-screen') || host;
  const wide = host.offsetWidth || screen.offsetWidth;
  const high = t.wrap.offsetHeight;
  // the title bar and xterm's own padding are there whatever the size, so they
  // are held apart from the grid of characters rather than averaged into it
  t.pad = [Math.max(0, wide - screen.offsetWidth),
           Math.max(0, high - screen.offsetHeight)];
  t.cell = [screen.offsetWidth / t.term.cols, screen.offsetHeight / t.term.rows];
  t.natural = [Math.ceil(wide), Math.ceil(high)];
}

// how big a tile has to be to hold this many characters
function span(t, cols, rows) {
  return [Math.round(cols * t.cell[0] + t.pad[0]),
          Math.round(rows * t.cell[1] + t.pad[1])];
}

// Pulling the corner is the same gesture as dragging the tile, so it is the
// same shape of code: the terminal is resized as you go, and the far end is
// told each time the count actually changes — which is what a real terminal
// does, and why a full-screen program redraws while you are still pulling.
function grab(e, w, el) {
  if (e.button) return;
  e.preventDefault();
  e.stopPropagation();
  const t = terms.get(w.term.session);
  if (!t || !t.cell) return;
  const sx = e.clientX, sy = e.clientY;
  const cols0 = t.term.cols, rows0 = t.term.rows;
  const tag = document.createElement('div');
  tag.className = 'termsize';
  el.append(tag);
  const show = () => { tag.textContent = `${t.term.cols}×${t.term.rows}`; };
  show();
  el.setPointerCapture(e.pointerId);
  const move = ev => {
    const cols = Math.max(20, Math.round(cols0 + (ev.clientX - sx) / zoom / t.cell[0]));
    const rows = Math.max(5, Math.round(rows0 + (ev.clientY - sy) / zoom / t.cell[1]));
    if (cols === t.term.cols && rows === t.term.rows) return;
    t.term.resize(cols, rows);
    t.natural = span(t, cols, rows);
    w.w = t.natural[0];
    w.h = t.natural[1];
    place(el, w);
    show();
    if (t.ws && t.ws.readyState === 1) {
      t.ws.send(JSON.stringify({ resize: { cols, rows } }));
    }
  };
  const done = ev => {
    try { el.releasePointerCapture(ev.pointerId); } catch (err) {}
    el.removeEventListener('pointermove', move);
    el.removeEventListener('pointerup', done);
    el.removeEventListener('pointercancel', done);
    tag.remove();
    measure(t);                      // what it settled at, measured not assumed
    hold(false);
    poll();
  };
  el.addEventListener('pointermove', move);
  el.addEventListener('pointerup', done);
  el.addEventListener('pointercancel', done);
}

async function newTerm() {
  const made = await fetch('/api/terminals', {
    method: 'POST',
    body: JSON.stringify({ cols: TERM_COLS, rows: TERM_ROWS }),
  }).then(r => r.json()).catch(() => null);
  if (made && made.id) { hold(true); poll(); }
}
$('#newterm').onclick = newTerm;

async function closeTerm(id) {
  await fetch('/api/terminals/' + id, { method: 'DELETE' }).catch(() => {});
  const t = terms.get(id);
  if (t && t.ws) t.ws.close();
  poll();
}

function renderCanvas(match, q) {
  if (fitting || !zoom) fitAll();
  $('#zoom').value = Math.round(Math.sqrt(zoom / MAX_ZOOM) * 100);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;

  const live = new Set();
  data.windows.slice().sort((a, b) => a.z - b.z).forEach(w => {
    live.add(w.id);
    let el = tileEls.get(w.id);
    if (!el) {
      el = document.createElement('div');
      if (!w.term) {
        el.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span></div>`;
        el.append(document.createElement('div'));
      }
      el.addEventListener('pointerdown', e => {
        const win = tileEls.get(w.id).win;
        if (win.term) {
          // the drag takes the pointer captive, and a captured pointer's click
          // is delivered to the tile rather than to what was under it — so the
          // close button has to be answered here, before any of that
          if (e.target.closest('.shut')) { e.preventDefault(); return closeTerm(win.term.session); }
          if (e.target.closest('.grip')) return grab(e, win, el);
          // a terminal is for typing into, so only its caption is a handle;
          // a photograph has nothing to click, so all of it is
          if (!e.target.closest('.cap')) return;
        }
        drag(e, win, el);
      });
      tileEls.set(w.id, el);
      $('#tiles').append(el);
    }
    el.win = w;                       // the drag handler always wants the fresh one
    el.className = 'tile' + (w.term ? ' term' : '') + (w.focused ? ' focused' : '')
      + (match(w) ? '' : ' off') + (w.id === sel ? ' sel' : '');
    if (w.term) {
      el.title = `${w.title} · pid ${w.pid}`;
      dressTerm(el, w);
    } else {
      el.title = `${w.app} — ${w.title} · workspace ${w.desktop + 1}`;
      el.querySelector('.dot').style.background = colorOf(w.app);
      el.querySelector('.t2').textContent = w.title;
      dress(el.lastElementChild, w);
    }
    place(el, w);
  });
  tileEls.forEach((el, id) => {
    if (live.has(id)) return;
    el.remove();
    tileEls.delete(id);
    const t = terms.get(id.slice(4));         // a session that has gone for good
    if (id.startsWith('web:') && t) {
      if (t.ws) t.ws.close();
      t.term.dispose();
      terms.delete(id.slice(4));
    }
  });
}

// ---- getting about: wheel, drag, and two fingers -------------------------

let letGo = null;   // how to call off whatever single-pointer gesture is running

$('#pan').addEventListener('wheel', e => {
  // A terminal has a scrollback of its own, and once it is big enough to read
  // it is a terminal rather than a tile: the wheel belongs to it. Zoomed out
  // far enough that nobody could read it, it is a tile again and the wheel
  // goes back to meaning zoom.
  if (zoom > 0.5 && e.target.closest('.termhost')) return;
  e.preventDefault();
  zoomAbout(zoom * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
}, { passive: false });

// one pointer anywhere on the background carries the whole surface with it
$('#canvas').addEventListener('pointerdown', e => {
  if (e.target.closest('.tile') || pointers.size > 1) return;   // one finger drags, two pinch
  const pan = $('#pan');
  let px = e.clientX, py = e.clientY;
  pan.classList.add('grabbing');
  const move = ev => { shift(ev.clientX - px, ev.clientY - py); px = ev.clientX; py = ev.clientY; };
  const done = () => {
    pan.classList.remove('grabbing');
    removeEventListener('pointermove', move);
    removeEventListener('pointerup', done);
    removeEventListener('pointercancel', done);
    hold(false);                 // you have said where you want to be looking
    letGo = null;
  };
  letGo = done;
  addEventListener('pointermove', move);
  addEventListener('pointerup', done);
  addEventListener('pointercancel', done);
});

// two fingers pinch to zoom and slide to pan, the pair working as one gesture
const pointers = new Map();
let pinch = null;

function pair() {
  const [a, b] = [...pointers.values()];
  return { gap: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

$('#pan').addEventListener('pointerdown', e => {
  if (e.pointerType === 'mouse') return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    if (letGo) letGo();            // a second finger means pinch, not drag
    const p = pair();
    pinch = { gap: p.gap, from: zoom, x: p.x, y: p.y };
  }
}, true);

$('#pan').addEventListener('pointermove', e => {
  if (!pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size !== 2 || !pinch) return;
  e.preventDefault();
  const now = pair();
  shift(now.x - pinch.x, now.y - pinch.y);
  pinch.x = now.x;
  pinch.y = now.y;
  // measured against where the fingers started, so the zoom cannot drift
  if (pinch.gap > 24) zoomAbout(pinch.from * (now.gap / pinch.gap), now.x, now.y);
}, true);

function liftFinger(e) {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) pinch = null;
}
addEventListener('pointerup', liftFinger, true);
addEventListener('pointercancel', liftFinger, true);

async function activate(id) {
  sel = id;
  render();
  if (id.startsWith('web:')) {
    // this one is already in front of you; focusing it means the keyboard
    const t = terms.get(id.slice(4));
    if (t) t.term.focus();
    return;
  }
  try { await fetch('/api/focus', { method: 'POST', body: JSON.stringify({ id }) }); }
  catch (e) {}
  poll();
}

// ---- keyboard picking -----------------------------------------------------
function selected() {
  if (!data) return null;
  return data.windows.find(w => w.id === sel) || null;
}

function reveal() {
  if (!sel) return;
  const w = data.windows.find(x => x.id === sel);
  const pan = $('#pan');
  if (!w || !pan.clientWidth) return;
  const [x, y] = seatOf(w);                       // bring the pick to the middle
  origin = [pan.clientWidth / 2 - (x + w.w / 2) * zoom,
            pan.clientHeight / 2 - (y + w.h / 2) * zoom];
  store.set('origin', origin);
  hold(false);
  $('#canvas').style.transform = `translate(${origin[0]}px,${origin[1]}px)`;
}

function move(dx, dy) {
  const match = visible();
  const pick = data.windows.filter(match);
  if (!pick.length) return;
  const cur = selected();
  if (!cur) { sel = pick[0].id; return (render(), reveal()); }

  if (dy && !dx) {                       // within a workspace, then on to the next one
    const here = ordered(cur.desktop).filter(match);
    const at = here.findIndex(w => w.id === cur.id);
    if (at + dy >= 0 && at + dy < here.length) { sel = here[at + dy].id; return (render(), reveal()); }
  }
  // the desktop's own grid is not what is on screen — the seating plan is, and
  // it has a cell for the terminals, which no workspace layout would ever hold
  const p = plan(), cells = [...p.at.keys()], n = cells.length;
  let i = Math.max(0, cells.indexOf(cur.desktop));
  for (let step = 0; step < n; step++) {
    i += dx + dy * p.cols;
    if (i < 0) i += n;
    if (i >= n) i -= n;
    const there = ordered(cells[i]).filter(match);
    if (there.length) { sel = there[dy > 0 ? 0 : there.length - 1].id; return (render(), reveal()); }
  }
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA') return;   // a terminal has the keyboard
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); sel = null; render(); }
    return;
  }
  const k = e.key;
  if (archbox.open) return;              // the dialog handles its own Esc
  if (k === 'a') { e.preventDefault(); return showArch(); }
  if (k === '/') { e.preventDefault(); $('#q').focus(); return; }
  if (k === 'Escape') {
    if ($('#q').value || sel) { $('#q').value = ''; sel = null; return render(); }
    return full ? setFull(false) : undefined;
  }
  if (k === 'f') { e.preventDefault(); return setFull(!full); }
  if (k === 't') { e.preventDefault(); return void newTerm(); }
  if (k === 'Enter' || k === ' ') { const w = selected(); if (w) { e.preventDefault(); activate(w.id); } return; }
  const moves = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                  ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] };
  if (moves[k]) { e.preventDefault(); move(...moves[k]); }
});

setFull(full);
render();
poll();
setInterval(poll, 2000);
</script>
"""


# ---- server ---------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    allow_focus = True

    def log_message(self, *a):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # a reloaded page walking away mid-poll is not an error

    def _send(self, body, ctype="application/json", code=200, cache=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _vendor(self, name):
        """xterm.js, from disk next to this script.

        The page is one string in this file and means to stay that way, but
        half a megabyte of terminal emulator is not going in it. Only these two
        names are ever served, and only from that one directory.
        """
        kind = {"xterm.js": "application/javascript", "xterm.css": "text/css"}.get(name)
        if not kind:
            return self._send(json.dumps({"error": "not found"}), code=404)
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
        try:
            with open(os.path.join(here, name), "rb") as f:
                body = f.read()
        except OSError:
            return self._send(json.dumps({"error": "vendor/%s is missing" % name}), code=404)
        self._send(body, kind + "; charset=utf-8", cache="public, max-age=86400")

    def do_GET(self):
        if self.path.startswith("/vendor/"):
            return self._vendor(self.path[len("/vendor/"):].split("?")[0])
        if self.path.startswith("/api/windows"):
            if SHOTS_ON and "screens=1" in self.path:
                watch_shots()
            self._send(json.dumps(sample()))
        elif self.path.startswith("/api/screen/"):
            try:
                data = shot_bytes(int(self.path.split("/")[3].split("?")[0]))
            except (IndexError, ValueError):
                data = b""
            if not data:
                return self._send(json.dumps({"error": "no photo of that workspace yet"}), code=404)
            # the url carries the capture time, so a given one never changes
            self._send(data, "image/jpeg", cache="private, max-age=300")
        elif self.path in ("/", "/index.html"):
            port = self.server.server_address[1]
            page = (PAGE.replace("__TITLE__", page_title(port))
                        .replace("_PORT_", ("%d" % port).ljust(6)[:6]))
            self._send(page, "text/html; charset=utf-8")
        else:
            self._send(json.dumps({"error": "not found"}), code=404)

    def do_POST(self):
        if self.path.startswith("/api/terminals"):
            if not PTY_ON:
                return self._send(json.dumps({"error": "terminals are off"}), code=403)
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            # starting a shell is slower than asking what exists, so give it room
            made = pty("/sessions", "POST", body, timeout=5)
            if made is None:
                return self._send(json.dumps({"error": _pty_error}), code=502)
            return self._send(json.dumps(made), code=201 if "id" in made else 400)
        if self.path.startswith("/api/focus"):
            return self.do_focus()
        return self._send(json.dumps({"error": "not found"}), code=404)

    def do_DELETE(self):
        if not self.path.startswith("/api/terminals/"):
            return self._send(json.dumps({"error": "not found"}), code=404)
        sid = self.path[len("/api/terminals/"):].split("?")[0]
        gone = pty("/sessions/" + sid, "DELETE", timeout=5)
        if gone is None:
            return self._send(json.dumps({"error": _pty_error}), code=502)
        self._send(json.dumps(gone))

    def do_focus(self):
        if not self.allow_focus:
            return self._send(json.dumps({"error": "focus disabled (--no-focus)"}), code=403)
        try:
            n = int(self.headers.get("Content-Length", 0))
            wid = json.loads(self.rfile.read(n) or b"{}").get("id", "")
        except (ValueError, json.JSONDecodeError):
            return self._send(json.dumps({"error": "bad request"}), code=400)
        ok, msg = focus(str(wid))
        if ok:
            hold_shots()  # the new workspace is worth a photo, but only once it is there
        self._send(json.dumps({"ok": ok, "msg": msg}), code=200 if ok else 400)


def main():
    global SHOTS_ON, SHOT_WIDTH, PTY_PORT, PTY_ON
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="show the page in the browser once serving")
    ap.add_argument("--no-focus", action="store_true", help="serve read-only, refuse focus requests")
    ap.add_argument("--no-screens", action="store_true",
                    help="never photograph the screen; the map stays a diagram")
    ap.add_argument("--shot-width", type=int, default=SHOT_WIDTH, metavar="PX",
                    help="width of each workspace photo (default %d)" % SHOT_WIDTH)
    ap.add_argument("--pty-port", type=int, default=PTY_PORT, metavar="N",
                    help="port for the terminals (default %d); one already "
                         "listening there is used as it stands" % PTY_PORT)
    ap.add_argument("--no-terminals", action="store_true",
                    help="do not hold terminals at all; the surface is real windows only")
    args = ap.parse_args()
    Handler.allow_focus = not args.no_focus
    SHOTS_ON = not args.no_screens
    SHOT_WIDTH = max(320, args.shot_width)
    PTY_ON = not args.no_terminals
    PTY_PORT = args.pty_port
    url = f"http://{args.host}:{args.port}/"
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        # the common case: launched a second time while one is already serving
        if args.open:
            print(f"winlist is already serving {url} — {show_page(url, args.port)}")
            return
        sys.exit(f"cannot listen on {args.host}:{args.port} ({e}) — "
                 f"another winlist is probably already running")
    if SHOTS_ON:
        threading.Thread(target=keep_shots, daemon=True).start()
    if args.open:
        threading.Thread(target=show_page, args=(url, args.port), daemon=True).start()

    pty_srv = start_terminals(PTY_PORT) if PTY_ON else None
    print(f"winlist → {url}  (Ctrl-C to stop)")
    if PTY_ON:
        print("terminals → :%d, %s" % (PTY_PORT, "ours, and they stop when this does"
                                       if pty_srv else "already running there, left alone"))

    # being killed is the ordinary way a server ends, and a shell must not
    # outlive this one either way, so SIGTERM comes in by the same door as Ctrl-C
    def hang_up(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, hang_up)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        stop_terminals(pty_srv)


if __name__ == "__main__":
    main()
