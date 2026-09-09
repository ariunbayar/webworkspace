#!/usr/bin/env python3
"""Open windows by workspace — live web dashboard, stdlib only.

Lists every visible window grouped into the workspace grid the desktop actually
uses, and focuses one on click or keyboard pick.

Run:  python3 winlist_server.py           # then open http://localhost:8766
      python3 winlist_server.py --port N  # custom port
      python3 winlist_server.py --open      # and bring the page up in the browser
      python3 winlist_server.py --no-focus  # read-only, refuse focus requests
      python3 winlist_server.py --no-screens  # never photograph the screen

X11 only: it reads EWMH properties via xprop/xdotool, and photographs the
workspace you are on with xwd + ImageMagick's convert.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import time
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
        with _shots_lock:
            _shots[desktop] = {"data": data, "at": time.time(),
                               "clock": time.strftime("%H:%M:%S"), "rects": rects}


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
    with _shots_lock:                       # where each window sat when its
        crops = {d: s["rects"] for d, s in _shots.items()}   # workspace was photographed

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
        })

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
    }


def focus(wid):
    """Raise a window and switch to its workspace."""
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
  .seg { display:flex; border:1px solid var(--line); border-radius:6px; overflow:hidden }
  .seg button { border:0; background:var(--panel); color:var(--dim); font:inherit; font-size:12px;
                padding:6px 12px; cursor:pointer; border-left:1px solid var(--line) }
  .seg button:first-child { border-left:0 }
  .seg button[aria-pressed=true] { background:var(--accent); color:#fff }
  .keys { margin-left:auto; color:var(--dim); font-size:11px }

  /* the whole browser window, without going properly fullscreen: the page just
     stops being a column of content and becomes the app */
  body.full .wrap { max-width:none; padding:10px 12px 16px }
  body.full h1, body.full footer, body.full .keys { display:none }
  body.full .sub { margin-bottom:8px }
  body.full .bar { margin-bottom:10px }
  /* the virtual screen is the one view that wants the viewport itself: the
     grids keep scrolling the page, which is what makes their rows size right */
  body.app { overflow:hidden }
  body.app .wrap { height:100vh; padding-bottom:10px; display:flex; flex-direction:column }
  body.app .pan { flex:1; min-height:0; height:auto }
  kbd { font:11px ui-monospace,monospace; border:1px solid var(--line); border-bottom-width:2px;
        border-radius:3px; padding:0 4px; background:var(--panel) }

  .grid { display:grid; gap:10px }
  .ws { border:1px solid var(--line); border-radius:8px; background:var(--panel);
        display:flex; flex-direction:column; overflow:hidden }
  .ws.empty { background:var(--empty); border-style:dashed }
  .ws.current { border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) }
  .wshead { display:flex; align-items:center; gap:6px; padding:5px 9px; font-size:11px;
            color:var(--dim); border-bottom:1px solid var(--line) }
  .ws.empty .wshead { border-bottom:0 }
  .wsnum { font-weight:700; color:var(--fg); font-size:12px; font-variant-numeric:tabular-nums }
  .rc { font-size:10px; opacity:.7 }
  .grow { flex:1 }
  .right { font-variant-numeric:tabular-nums }
  .age { font-size:10px; opacity:.7; font-variant-numeric:tabular-nums; margin-right:6px }
  .age.live { color:var(--accent); opacity:1 }
  .here { font-size:9.5px; text-transform:uppercase; letter-spacing:.05em;
          background:var(--accent); color:#fff; padding:1px 6px; border-radius:99px }
  ul { list-style:none; margin:0; padding:4px; display:flex; flex-direction:column; gap:1px; flex:1 }
  li { display:flex; align-items:center; gap:6px; padding:3px 5px; border-radius:4px;
       min-width:0; cursor:pointer }
  li.win { padding-left:16px }
  li.head { cursor:default; color:var(--dim); font-size:10.5px; letter-spacing:.03em;
            padding:4px 5px 1px; text-transform:uppercase }
  li.head:hover { background:none }
  li.head + li.win, li.win + li.win { border-left:1px solid var(--line); margin-left:8px;
                                      padding-left:8px; border-radius:0 4px 4px 0 }
  li:hover:not(.head) { background:var(--chip) }
  li.focused { background:color-mix(in srgb, var(--accent) 15%, transparent) }
  li.sel, .rect.sel { outline:2px solid var(--accent); outline-offset:-1px }
  li.off { opacity:.28 }
  .dot { width:7px; height:7px; border-radius:2px; flex:none }
  .t2 { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px }
  .app { color:var(--dim); font-size:10.5px; flex:none }
  /* aspect-ratio, not percentage padding: a percentage would resolve against an
     indefinite width while the grid sizes its rows, and the cell would collapse */
  .map { position:relative; flex:none; margin:6px; border:1px solid var(--line);
         border-radius:4px; background:var(--empty); overflow:hidden }
  .map .shot { position:absolute; inset:0; width:100%; height:100%; display:block }
  .rect { position:absolute; border-radius:2px; overflow:hidden; padding:1px 3px; font-size:9px;
          line-height:1.2; color:#fff; text-shadow:0 1px 1px rgba(0,0,0,.5); cursor:pointer;
          border:1px solid rgba(0,0,0,.28) }
  .rect.off { opacity:.25 }
  /* over a photo the rectangle is just an outline — the picture is the content */
  .rect.over { background:transparent; border-color:transparent; padding:0;
               box-shadow:inset 0 0 0 2px var(--c) }
  .rect.over .lbl { display:inline-block; max-width:100%; padding:1px 4px; border-radius:0 0 3px 0;
                    background:var(--c); opacity:0; transition:opacity .12s;
                    overflow:hidden; text-overflow:ellipsis; white-space:nowrap }
  .rect.over:hover .lbl, .rect.over.sel .lbl, .rect.over.hit .lbl { opacity:1 }
  .rect.over.off { opacity:1; background:rgba(0,0,0,.62); box-shadow:none }
  .rect.over.off .lbl { display:none }
  .waiting { position:absolute; left:50%; bottom:5px; transform:translateX(-50%); z-index:20;
             font-size:9.5px; color:var(--dim); pointer-events:none; white-space:nowrap;
             background:var(--panel); border:1px solid var(--line); border-radius:99px;
             padding:1px 7px; opacity:.9 }
  .blank { flex:1; min-height:32px }

  /* the virtual screen: every window on one surface, arranged however you like */
  .ctl { display:none; gap:8px; align-items:center }
  .btn { border:1px solid var(--line); background:var(--panel); color:var(--dim); font:inherit;
         font-size:12px; padding:5px 10px; border-radius:6px; cursor:pointer }
  .btn:hover { color:var(--fg); border-color:var(--dim) }
  .btn[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:#fff }
  #full { font-size:14px; line-height:1; padding:5px 9px }
  #zoom { width:96px; accent-color:var(--accent) }
  /* the surface is placed, not scrolled: overflow is hidden and the canvas is
     translated, so a drag can carry everything as far as you like */
  .pan { display:none; position:relative; overflow:hidden; border:1px solid var(--line);
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
  .pic { flex:1; min-height:0; background-repeat:no-repeat; background-origin:border-box }
  .pic.none { display:flex; align-items:center; justify-content:center; color:#fff;
              font-size:10px; text-shadow:0 1px 2px rgba(0,0,0,.4) }
  footer { color:var(--dim); font-size:11px; margin-top:18px; border-top:1px solid var(--line); padding-top:9px }
  code { font-size:10.5px; background:var(--chip); padding:1px 4px; border-radius:3px }
</style>
<div class="wrap">
  <h1>Open windows</h1>
  <div class="sub"><b id="stat">loading…</b> · <span id="ts"></span></div>
  <div class="bar">
    <input type="search" id="q" placeholder="Filter title or app…">
    <div class="seg" id="view">
      <button data-v="list" aria-pressed="true">Titles</button>
      <button data-v="map" aria-pressed="false">Map</button>
      <button data-v="canvas" aria-pressed="false">Screen</button>
    </div>
    <button id="full" class="btn" aria-pressed="false"
            title="Give it the whole browser window (f)">⤢</button>
    <span class="ctl" id="ctl">
      <input type="range" id="zoom" min="2" max="100" step="1" title="Zoom">
      <button id="fit" class="btn">Fit</button>
      <button id="reset" class="btn">Reset layout</button>
    </span>
    <span class="keys"><kbd>↑↓←→</kbd>/<kbd>hjkl</kbd> pick · <kbd>Enter</kbd> focus ·
      <kbd>/</kbd> filter · <kbd>f</kbd> full window · <kbd>Esc</kbd> clear</span>
  </div>
  <div class="grid" id="grid"></div>
  <div class="pan" id="pan"><div class="canvas" id="canvas"><div id="tiles"></div></div></div>
  <footer id="foot"></footer>
</div>
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
let view = store.get('view', 'list');
let full = store.get('full', false);       // fill the browser window, F11 not involved
let layout = store.get('layout', {});      // window id -> [x, y] on the virtual screen
let zoom = store.get('zoom', 0);           // 0 until we have measured a fit
let origin = store.get('origin', [0, 0]);  // where the surface sits in the frame
let fitting = store.get('fitting', true);  // keep fitting until you take the wheel
const GUTTER = 140;                        // virtual px between one workspace and the next

// One <img> per workspace, kept across renders: re-appending the same node
// leaves the picture on screen, so nothing blinks and nothing is refetched
// until the capture time in its url actually moves.
const shotEls = new Map();
function shotUrl(i) {
  const s = data.shots && data.shots[i];
  return s ? `/api/screen/${i}?v=${encodeURIComponent(s.clock)}` : null;
}
function shotFor(i) {
  const src = shotUrl(i);
  if (!src) return null;
  let img = shotEls.get(i);
  if (!img) { img = new Image(); img.className = 'shot'; img.alt = ''; shotEls.set(i, img); }
  if (img.getAttribute('src') !== src) img.setAttribute('src', src);
  return img;
}
const ago = s => s < 3 ? 'live' : s < 60 ? Math.round(s) + 's'
  : s < 3600 ? Math.round(s / 60) + 'm' : Math.round(s / 3600) + 'h';

function setView(v) {
  view = v;
  store.set('view', v);
  [...$('#view').children].forEach(x => x.setAttribute('aria-pressed', x.dataset.v === v));
  render();
}
$('#view').onclick = e => { const b = e.target.closest('button'); if (b) setView(b.dataset.v); };

function setFull(v) {
  full = v;
  store.set('full', v);
  document.body.classList.toggle('full', v);
  $('#full').setAttribute('aria-pressed', v);
  render();
}
$('#full').onclick = () => setFull(!full);
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
addEventListener('resize', () => { if (view === 'canvas') render(); });
$('#q').addEventListener('input', () => { sel = null; render(); });

async function poll() {
  try {
    // asking for screens is what keeps the grabber awake, so only the views that
    // show photographs do it
    const wants = view === 'map' || view === 'canvas';
    const r = await fetch('/api/windows' + (wants ? '?screens=1' : ''));
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
  const match = visible(), q = $('#q').value.trim(), canvas = view === 'canvas';
  document.body.classList.toggle('app', full && canvas);
  $('#grid').style.display = canvas ? 'none' : 'grid';
  $('#pan').style.display = canvas ? 'block' : 'none';
  $('#ctl').style.display = canvas ? 'flex' : 'none';
  if (canvas) renderCanvas(match, q); else renderGrid(match, q);
  status(match, q);
}

function renderGrid(match, q) {
  const grid = $('#grid');
  grid.style.gridTemplateColumns = `repeat(${data.grid.cols}, minmax(0,1fr))`;
  grid.innerHTML = "";
  // one cell per workspace, row-major, empty ones included so positions hold still
  for (let i = 0; i < data.grid.cols * data.grid.rows; i++) {
    const ws = onWorkspace(i);
    const card = document.createElement('section');
    card.className = 'ws' + (ws.length ? '' : ' empty') + (i === data.current ? ' current' : '');
    const row = Math.floor(i / data.grid.cols) + 1, col = i % data.grid.cols + 1;
    const shot = data.shots ? data.shots[i] : null;
    card.innerHTML = `<div class="wshead"><span class="wsnum">${i + 1}</span>
      <span class="rc">r${row}c${col}</span><span class="grow"></span>
      ${view === 'map' && shot
        ? `<span class="age${shot.age < 3 ? ' live' : ''}">${ago(shot.age)}</span>` : ''}
      ${i === data.current ? '<span class="here">here</span>'
        : `<span class="right">${ws.length || ''}</span>`}</div>`;
    if (!ws.length) { card.innerHTML += '<div class="blank"></div>'; grid.append(card); continue; }
    if (view === 'map') {
      const img = shotFor(i);
      card.innerHTML += `<div class="map" style="aspect-ratio:${data.screen.w}/${data.screen.h}">`
        + (img || !data.shots_on || data.shot_error ? ''
           : '<span class="waiting">no photo yet — visit this workspace</span>') + '</div>';
      const map = card.querySelector('.map');
      if (img) map.prepend(img);
      [...ws].reverse().forEach(w => {          // bottom of the stack painted first
        const r = document.createElement('div');
        r.className = 'rect' + (img ? ' over' : '') + (match(w) ? '' : ' off')
          + (w.id === sel ? ' sel' : '') + (q && match(w) ? ' hit' : '');
        r.style.cssText = `left:${Math.max(0, w.x) / data.screen.w * 100}%;
          top:${Math.max(0, w.y) / data.screen.h * 100}%;
          width:${Math.min(w.w, data.screen.w) / data.screen.w * 100}%;
          height:${Math.min(w.h, data.screen.h) / data.screen.h * 100}%;
          --c:${colorOf(w.app)};${img ? '' : `background:${colorOf(w.app)};`}`
          + (w.focused ? 'z-index:9' : '');
        r.innerHTML = `<span class="lbl">${esc(w.title)}</span>`;
        r.title = `${w.app} — ${w.title}`;
        r.onclick = () => activate(w.id);
        map.append(r);
      });
    } else {
      const ul = document.createElement('ul');
      byApp(ws).forEach(([app, group]) => {
        const head = document.createElement('li');
        head.className = 'head';
        head.innerHTML = `<span class="dot" style="background:${colorOf(app)}"></span>
          <span class="t2">${esc(app)}</span>
          <span class="app">${group.length > 1 ? group.length : ''}</span>`;
        ul.append(head);
        group.forEach(w => {
          const li = document.createElement('li');
          li.className = 'win' + (w.focused ? ' focused' : '') + (match(w) ? '' : ' off')
            + (w.id === sel ? ' sel' : '');
          li.title = `${w.app} · pid ${w.pid} · ${w.id}`;
          li.innerHTML = `<span class="t2">${esc(w.title)}</span>`;
          li.onclick = () => activate(w.id);
          ul.append(li);
        });
      });
      card.append(ul);
    }
    grid.append(card);
  }
}

function status(match, q) {
  const hits = data.windows.filter(match);
  $('#stat').textContent = `${hits.length}${q ? " of " + data.windows.length : ""} windows · `
    + `${data.grid.cols}×${data.grid.rows} workspaces · ${new Set(data.windows.map(w => w.desktop)).size} in use`;
  $('#ts').innerHTML = failures ? `<span class="stale">disconnected — retrying</span>`
    : `updated ${data.captured}`;
  if (view === 'canvas') {
    return void ($('#foot').innerHTML = `Every window on one surface, seeded from where it `
      + `really sits and then yours to arrange: drag a tile and only the tile moves — the `
      + `desktop is never touched. The arrangement is remembered in this browser; `
      + `<b>Reset layout</b> puts everything back where the desktop has it. Scroll or `
      + `pinch to zoom, drag the background or slide two fingers to pan, and click a window `
      + `(or press <kbd>Enter</kbd>) to focus it for real. Windows start out grouped by `
      + `the workspace they live on, packed together rather than spread over the desktop's `
      + `own grid.`);
  }
  $('#foot').innerHTML = `Grid from ${data.grid.source} `
    + `(<code>${data.grid.cols}</code> × <code>${data.grid.rows}</code>, row-major); `
    + `windows placed by <code>_NET_WM_DESKTOP</code>, app resolved from WM_CLASS plus the `
    + `process running inside the window. Click a window or press <kbd>Enter</kbd> to focus it.`
    + (view !== 'map' ? '' : !data.shots_on
        ? ` Screens off (<code>--no-screens</code>), so the map stays a diagram.`
        : data.shot_error
        ? ` No screens: ${esc(data.shot_error)}.`
        : ` X can only photograph the workspace in front of you, so each cell shows the last `
          + `look at it and how long ago that was; visit a workspace to fill its cell in.`);
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
  if (!url || !cw || !ch) {
    pic.className = 'pic none';
    pic.style.cssText = `background:${colorOf(w.app)}`;
    pic.textContent = data.shots_on ? 'not photographed yet' : '';
    return;
  }
  pic.className = 'pic';
  pic.textContent = '';
  pic.style.cssText = `background-image:url("${url}");`
    + `background-size:${S.w / cw * 100}% ${S.h / ch * 100}%;`
    + `background-position:${S.w > cw ? x / (S.w - cw) * 100 : 0}% `
    + `${S.h > ch ? y / (S.h - ch) * 100 : 0}%`;
}

function place(el, w) {
  const [x, y] = seatOf(w);
  el.style.left = x * zoom + 'px';
  el.style.top = y * zoom + 'px';
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
      el.innerHTML = `<div class="cap"><span class="dot"></span><span class="t2"></span></div>`;
      el.append(document.createElement('div'));
      el.addEventListener('pointerdown', e => drag(e, tileEls.get(w.id).win, el));
      tileEls.set(w.id, el);
      $('#tiles').append(el);
    }
    el.win = w;                       // the drag handler always wants the fresh one
    el.className = 'tile' + (w.focused ? ' focused' : '') + (match(w) ? '' : ' off')
      + (w.id === sel ? ' sel' : '');
    el.title = `${w.app} — ${w.title} · workspace ${w.desktop + 1}`;
    el.querySelector('.dot').style.background = colorOf(w.app);
    el.querySelector('.t2').textContent = w.title;
    dress(el.lastElementChild, w);
    place(el, w);
  });
  tileEls.forEach((el, id) => { if (!live.has(id)) { el.remove(); tileEls.delete(id); } });
}

// ---- getting about: wheel, drag, and two fingers -------------------------

let letGo = null;   // how to call off whatever single-pointer gesture is running

$('#pan').addEventListener('wheel', e => {
  if (view !== 'canvas') return;
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
  if (view !== 'canvas' || !sel) return;
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
  const cols = data.grid.cols, cells = cols * data.grid.rows;
  let i = cur.desktop;
  for (let step = 0; step < cells; step++) {   // walk the grid to the next occupied cell
    i += dx + dy * cols;
    if (i < 0) i += cells;
    if (i >= cells) i -= cells;
    const there = ordered(i).filter(match);
    if (there.length) { sel = there[dy > 0 ? 0 : there.length - 1].id; return (render(), reveal()); }
  }
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); sel = null; render(); }
    return;
  }
  const k = e.key;
  if (k === '/') { e.preventDefault(); $('#q').focus(); return; }
  if (k === 'Escape') {
    if ($('#q').value || sel) { $('#q').value = ''; sel = null; return render(); }
    return full ? setFull(false) : undefined;
  }
  if (k === 'f') { e.preventDefault(); return setFull(!full); }
  if (k === 'Enter' || k === ' ') { const w = selected(); if (w) { e.preventDefault(); activate(w.id); } return; }
  const moves = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                  ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] };
  if (moves[k]) { e.preventDefault(); move(...moves[k]); }
});

setFull(full);
setView(view);
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

    def do_GET(self):
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
            page = PAGE.replace("__TITLE__", page_title(self.server.server_address[1]))
            self._send(page, "text/html; charset=utf-8")
        else:
            self._send(json.dumps({"error": "not found"}), code=404)

    def do_POST(self):
        if not self.path.startswith("/api/focus"):
            return self._send(json.dumps({"error": "not found"}), code=404)
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
    global SHOTS_ON, SHOT_WIDTH
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="show the page in the browser once serving")
    ap.add_argument("--no-focus", action="store_true", help="serve read-only, refuse focus requests")
    ap.add_argument("--no-screens", action="store_true",
                    help="never photograph the screen; the map stays a diagram")
    ap.add_argument("--shot-width", type=int, default=SHOT_WIDTH, metavar="PX",
                    help="width of each workspace photo (default %d)" % SHOT_WIDTH)
    args = ap.parse_args()
    Handler.allow_focus = not args.no_focus
    SHOTS_ON = not args.no_screens
    SHOT_WIDTH = max(320, args.shot_width)
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
    print(f"winlist → {url}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
