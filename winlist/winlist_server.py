#!/usr/bin/env python3
"""Open windows by workspace — live web dashboard, stdlib only.

Lists every visible window grouped into the workspace grid the desktop actually
uses, and focuses one on click or keyboard pick.

Run:  python3 winlist_server.py           # then open http://localhost:8766
      python3 winlist_server.py --port N  # custom port
      python3 winlist_server.py --open      # and bring the page up in the browser
      python3 winlist_server.py --no-focus  # read-only, refuse focus requests
      python3 winlist_server.py --no-screens  # never photograph the screen
      python3 winlist_server.py --install     # run it as a service from now on
      python3 winlist_server.py --uninstall   # back to running it by hand

In a terminal, r restarts it and Ctrl-C stops it. As a service it is a systemd
user unit, winlist.service, started with the desktop session and logging to the
journal: systemctl --user restart|stop|status winlist, journalctl --user -u winlist.

Terminals the page started itself sit on the same surface as the real windows,
drawn by xterm.js rather than photographed. pty_server.py holds them; this
starts it when nobody has, as a process of its own, so restarting this one
leaves your shells where they were. `pkill -f pty_server.py` ends them.

X11 only: it reads EWMH properties via xprop/xdotool, and photographs the
workspace you are on with xwd + ImageMagick's convert.
"""
import argparse
import html
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WIN_ID = re.compile(r"^0x[0-9a-fA-F]+$")

STARTED = time.time()   # tells a restarted server from the one it replaced (exec keeps the pid)

# ---- shelling out ---------------------------------------------------------


def say(msg):
    """A line on the terminal, stamped with when it was said."""
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def sh(*args, timeout=5):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def prop(text, name):
    """Value of one property out of a multi-property xprop dump.

    xprop prints either `NAME(TYPE) = value` or, for window lists,
    `NAME(WINDOW): window id # 0xa, 0xb`. A property the window does not
    have comes out as `NAME:  not found.`, which is no value at all."""
    m = re.search(r"^%s(?:\([^)]*\))?\s*[=:]\s*(.*)$" % re.escape(name), text, re.M)
    v = m.group(1).strip() if m else ""
    return "" if v == "not found." else v


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


def pretty_class(cls):
    """A WM_CLASS nobody named, made readable: org.gnome.Nautilus is Nautilus,
    jetbrains-idea is Jetbrains Idea."""
    last = (cls or "").rsplit(".", 1)[-1].replace("-", " ").replace("_", " ").strip()
    return " ".join(p[:1].upper() + p[1:] for p in last.split()) or "Unknown"


def resolve_app(cls, pid, ttl=8):
    cached = _app_cache.get(pid)
    now = time.time()
    if cached and cached[0] > now:
        return cached[1]

    key = cls.lower()
    app = PRETTY.get(key) or PRETTY.get(key.rsplit(".", 1)[-1]) or pretty_class(cls)
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


# What a terminal should look like is a thing you have already decided once,
# in ~/.Xresources, and the xterm you are used to reads it from there. So does
# this: the palette, the font, the size a new one opens at. Only the plain
# XTerm class — a `font-cozette*` or any other named class is a profile you
# asked for by name, not the default you get by typing `xterm`.
XTERM_CLASS = "XTerm*"
ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
        "brightBlack", "brightRed", "brightGreen", "brightYellow",
        "brightBlue", "brightMagenta", "brightCyan", "brightWhite"]
LOOK = {}          # read once at startup; nothing here changes while we run


def web_face(face):
    """The face to hand the browser for an X face.

    A bitmap face like Cozette is drawn by Chrome only at its own pixel size
    and never under a transform, and a terminal tile is always scaled with the
    surface — so it comes out blank. Its outline twin (CozetteVector) scales,
    so that is used instead when it is installed. Without fc-list, as given.
    """
    if not face or sh("fc-list", face + ":scalable=true", "family").strip():
        return face
    twin = face + "Vector"
    return twin if sh("fc-list", twin + ":scalable=true", "family").strip() else face


def xterm_look():
    """Read the default XTerm resources, as far as a browser can honour them."""
    lines = sh("xrdb", "-query").splitlines()
    res, named = {}, {}
    for line in lines:
        key, sep, val = line.partition(":")
        if sep and key.startswith(XTERM_CLASS):
            res[key[len(XTERM_CLASS):].strip().lower()] = val.strip()
        # the named profiles are only read for their face, to switch to
        m = sep and re.match(r"(font-[\w-]+)\*(\w+)$", key.strip())
        if m:
            named.setdefault(m.group(1), {})[m.group(2).lower()] = val.strip()
    if not res:
        return {}

    look, theme = {}, {}
    for name, colour in (("background", res.get("background")),
                         ("foreground", res.get("foreground")),
                         ("cursor", res.get("cursorcolor"))):
        if colour:
            theme[name] = colour
    for i, name in enumerate(ANSI):
        colour = res.get("color%d" % i)
        if colour:
            theme[name] = colour
    if theme:
        look["theme"] = theme
    if res.get("facename"):
        look["font"] = web_face(res["facename"])
    for key, name, cast in (("facesize", "size", float), ("savelines", "scrollback", int)):
        try:
            look[name] = cast(res[key])
        except (KeyError, ValueError):
            pass
    # faceSize is in points, as Xft takes it; the browser wants pixels
    dpi = re.search(r"^Xft\.dpi:\s*([\d.]+)", "\n".join(lines), re.M)
    px = lambda pt: round(pt * (float(dpi.group(1)) if dpi else 96) / 72, 2)
    if "size" in look:
        look["size"] = px(look["size"])
    # The faces a terminal can be switched between: the default first, named
    # after its own face, then each `font-*` profile under its own name
    if look.get("font"):
        profiles = [{"name": res["facename"].split()[0].lower(), "font": look["font"],
                     "size": look.get("size")}]
        for name, r in sorted(named.items()):
            if not r.get("facename"):
                continue
            try:
                size = px(float(r["facesize"]))
            except (KeyError, ValueError):
                size = look.get("size")
            profiles.append({"name": name.removeprefix("font-"), "font": web_face(r["facename"]),
                             "size": size})
        if len(profiles) > 1:
            look["profiles"] = profiles
    if "cursorblink" in res:
        look["blink"] = res["cursorblink"].lower() == "true"
    # bold text in a brighter colour is xterm's boldColors, off by default here
    # only because that is what the resource says
    if "boldcolors" in res:
        look["bold_bright"] = res["boldcolors"].lower() == "true"
    size = re.match(r"(\d+)x(\d+)", res.get("geometry", ""))
    if size:
        look["cols"], look["rows"] = int(size.group(1)), int(size.group(2))
    return look


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


# The page's terminals are remembered here, so a reboot or a new pty_server
# can offer them back: session id -> {cwd, cols, rows, claude, at, face}. The
# server knows the first four, and its last title; the page says where a tile
# sits and its face. Closed on purpose, or ended, and it is forgotten.
# pty_server keeps each one's last output and commands beside it, in terms/.
TERMS_FILE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                          "winlist", "terms.json")
TERMS_DIR = os.path.join(os.path.dirname(TERMS_FILE), "terms")
_terms_lock = threading.Lock()
_live = None                        # session ids pty_server holds now; None: not asked yet


def _load_terms():
    try:
        with open(TERMS_FILE) as f:
            return {k: v for k, v in json.load(f).items() if isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        return {}


_terms = _load_terms()


def _save_terms():
    """Called holding _terms_lock."""
    try:
        os.makedirs(os.path.dirname(TERMS_FILE), exist_ok=True)
        with open(TERMS_FILE + ".tmp", "w") as f:
            json.dump(_terms, f)
        os.replace(TERMS_FILE + ".tmp", TERMS_FILE)
    except OSError:
        pass                        # still remembered, just not past a restart


def _term_file(sid, ext):
    """Where a session's saved output (.out) or commands (.cmds) are; None for an id that is no session's."""
    return os.path.join(TERMS_DIR, sid + ext) if isinstance(sid, str) and re.fullmatch(r"\d{1,9}", sid) else None


def _forget_files(sid):
    for ext in (".out", ".cmds"):
        try:
            os.unlink(_term_file(sid, ext))
        except (OSError, TypeError):
            pass


def _last_cmds(sid, n=3):
    try:
        with open(_term_file(sid, ".cmds"), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return []
    return [l[:300] for l in lines if l.strip()][-n:]


def scrollback(sid):
    """The saved output of a remembered terminal (at most 64 KB), or None."""
    with _terms_lock:
        known = sid in _terms
    try:
        with open(_term_file(sid, ".out"), "rb") as f:
            return f.read(256 * 1024) if known else None
    except (OSError, TypeError):
        return None


def note_terms(sessions):
    """What pty_server holds now: remember each live one, forget one that ended."""
    global _live
    with _terms_lock:
        before = json.dumps(_terms, sort_keys=True)
        _live = {t["id"] for t in sessions}
        for t in sessions:
            if not t.get("alive"):
                if _terms.pop(t["id"], None) is not None:
                    _forget_files(t["id"])
                continue
            claude = t.get("argv") == ["claude"] or t.get("running") == "claude"
            _terms.setdefault(t["id"], {}).update(
                cwd=t.get("cwd") or "", cols=t.get("cols", 80), rows=t.get("rows", 24), claude=claude)
            if t.get("title"):
                _terms[t["id"]]["title"] = t["title"][:200]
        if json.dumps(_terms, sort_keys=True) != before:
            _save_terms()


def lost_terms():
    """Remembered terminals whose sessions are gone: the new pty_server never had them."""
    with _terms_lock:
        if _live is None:
            return []
        return [dict(v, id=k, cwd_ok=os.path.isdir(v.get("cwd") or ""), cmds=_last_cmds(k))
                for k, v in _terms.items() if k not in _live and "cwd" in v]


def term_session(window, session):
    """Remember which Claude session a page terminal runs, for --resume."""
    sid = window[4:] if isinstance(window, str) and window.startswith("web:") else None
    if not sid or not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,64}", session):
        return
    with _terms_lock:
        if sid in _terms and _terms[sid].get("session") != session:
            _terms[sid]["session"] = session
            _save_terms()


def change_term(sid, body):
    """Where the page has a terminal's tile and which face; body None forgets it."""
    with _terms_lock:
        if body is None:
            if _terms.pop(sid, None) is not None:
                _save_terms()
            _forget_files(sid)
            return True
        if sid not in _terms:
            return False
        at, face = body.get("at"), body.get("face")
        if (isinstance(at, list) and len(at) == 2
                and all(isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e7 for v in at)):
            _terms[sid]["at"] = [round(v) for v in at]
        if isinstance(face, str):
            _terms[sid]["face"] = face[:100]
        _save_terms()
        return True


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
    if isinstance(answer.get("sessions"), list):    # an error answer is no list of sessions
        note_terms(answer["sessions"])
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
                "title": t.get("title", ""),
                "age": t.get("age", 0),
            },
        })
        x += wide + GAP
    return out


def start_terminals(port):
    """Start the terminal server, unless one is already listening.

    It runs as a process of its own, in a session of its own, so it outlives
    this one: restarting winlist to pick up a change should not take your shells
    with it. One already there — left by an earlier winlist, or started by
    hand — is simply used. Says which of the two it was.
    """
    global _pty_error
    if pty("/sessions") is not None:
        return "already running there, used as it stands"
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pty_server.py")
    if not os.path.exists(here):
        _pty_error = "no terminal server here to run"
        return None
    proc = subprocess.Popen([sys.executable, here, "--port", str(port)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(20):
        time.sleep(0.1)
        if pty("/sessions") is not None:
            return "started, and kept across restarts (pid %d)" % proc.pid
        if proc.poll() is not None:
            break
    return None


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
        if not title:
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
        "started": STARTED,
        "pty": {"on": PTY_ON, "port": PTY_PORT, "cell": n_desktops, "error": _pty_error},
        "look": LOOK,          # what your xterm looks like, for ours to match
        "links": board(),       # the cards on the board, the same in every browser
        "arrange": arrangement(),  # its groups and tile places; None until a page sends one
        "lost": lost_terms(),   # terminals a reboot took, for the page to offer back
        "pings": pinged(),      # windows that want you, the same in every browser
        "claude": claude_states({w["id"] for w in windows}),  # what Claude is up to in each
    }


# The cards on the board — pages, documents, pictures — are kept here, not in
# the browser, so every browser shows the same board. Each has an id, and once
# a page has placed it, where it sits and how big it is. On disk, so a restart
# keeps the board.
LINKS_FILE = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                          "winlist", "links.json")
_links_lock = threading.Lock()


def _load_links():
    try:
        with open(LINKS_FILE) as f:
            return [l for l in json.load(f) if isinstance(l, dict) and "id" in l]
    except (OSError, ValueError):
        return []


_links = _load_links()


# What the page is used for, one line per thing done, so a change to it can be
# judged by whether it changed how it is used. Names and counts only — never a
# title, a URL or anything typed. `usage_report.py` reads it back.
USAGE_FILE = os.path.join(os.path.dirname(LINKS_FILE), "usage.jsonl")
USAGE_MAX = 20 * 1024 * 1024        # past this it stops growing rather than fill the disk
_usage_lock = threading.Lock()


def log_usage(events):
    if not isinstance(events, list):
        return 0
    lines = []
    for e in events[:500]:
        if not isinstance(e, dict) or not isinstance(e.get("ev"), str) or len(e["ev"]) > 40:
            continue
        line = json.dumps({k: v for k, v in e.items()
                           if isinstance(k, str) and isinstance(v, (str, int, float, bool))
                           and len(str(v)) <= 60}, separators=(",", ":"))
        if len(line) <= 400:
            lines.append(line)
    if not lines:
        return 0
    with _usage_lock:
        try:
            os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
            if os.path.exists(USAGE_FILE) and os.path.getsize(USAGE_FILE) > USAGE_MAX:
                return 0
            with open(USAGE_FILE, "a") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            return 0
    return len(lines)


def fetch_title(url):
    """What the page calls itself, if it will say without a login: else None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 winlist"})
        with urllib.request.urlopen(req, timeout=3) as r:
            if "html" not in r.headers.get("Content-Type", ""):
                return None
            head = r.read(65536).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except (OSError, ValueError):
        return None
    m = re.search(r"<title[^>]*>(.*?)</title>", head, re.S | re.I)
    return html.unescape(" ".join(m.group(1).split()))[:200] if m else None


# A GitHub issue or PR card says whether it is still open, so a finished one
# can be thrown away. gh does the asking, so private repos answer too; each
# answer is kept a minute, which is as often as the page asks.
_gh = {}


def gh_state(url):
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/(pull|issues)/(\d+)", url or "")
    if not m:
        return None
    hit = _gh.get(url)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    owner, repo, _, n = m.groups()
    try:
        out = subprocess.run(
            ["gh", "api", "repos/%s/%s/issues/%s" % (owner, repo, n),
             "--jq", "[.state, .state_reason, .pull_request != null, .pull_request.merged_at, .title]"],
            capture_output=True, text=True, timeout=8)
        st, reason, pr, merged, title = json.loads(out.stdout)
        state = ("merged" if merged else "not planned" if reason == "not_planned" else st)
        answer = {"state": state, "pr": pr, "title": title}
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        answer = None
    _gh[url] = (time.time(), answer)
    return answer


# A text file shown on the surface is read from disk each time it changes,
# so it reads like the editor it was written in. Any text file, and only to
# this page: the answer is the file itself, unlike anything else here.
MD_EXT = (".md", ".markdown")


def is_text(path):
    # binary if the start has a NUL or is not utf-8; a character cut by the
    # 8 KB boundary is fine, so a cut-off tail is not held against it
    with open(path, "rb") as f:
        head = f.read(8192)
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:
        return len(head) == 8192 and e.start >= len(head) - 3 and e.reason == "unexpected end of data"
    return True


def read_doc(path, since=None):
    path = os.path.abspath(os.path.expanduser(path or ""))
    try:
        st = os.stat(path)
        if not os.path.isfile(path) or st.st_size > 2 << 20:
            return None, "not a file, or over 2 MB"
        if not is_text(path):
            return None, "not a text file"
        out = {"path": path, "name": os.path.basename(path), "mtime": st.st_mtime_ns,
               "kind": "md" if path.lower().endswith(MD_EXT) else "text"}
        if str(st.st_mtime_ns) != since:
            with open(path, encoding="utf-8", errors="replace") as f:
                out["text"] = f.read()
        return out, None
    except OSError as e:
        return None, e.strerror or "cannot read it"


# Pictures go on the surface the same way: a file on disk is handed out by
# path, only to this page and only if it is an image; one on the web is not
# fetched here at all, the page shows it from where it is.
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
             ".bmp": "image/bmp", ".avif": "image/avif"}


def image_file(path):
    path = os.path.abspath(os.path.expanduser(path or ""))
    kind = IMG_TYPES.get(os.path.splitext(path)[1].lower())
    if not kind:
        return None, None, "only " + ", ".join(sorted(IMG_TYPES)) + " images"
    if not os.path.isfile(path) or os.path.getsize(path) > 30 << 20:
        return None, None, "not a file, or over 30 MB"
    return path, kind, None


def board():
    with _links_lock:
        return [dict(l) for l in _links]


def _save_links():
    """Called holding _links_lock."""
    try:
        os.makedirs(os.path.dirname(LINKS_FILE), exist_ok=True)
        with open(LINKS_FILE + ".tmp", "w") as f:
            json.dump(_links, f)
        os.replace(LINKS_FILE + ".tmp", LINKS_FILE)
    except OSError:
        pass                            # still on the board, just not past a restart


# The groups and where the tiles sit are kept beside the cards, for the same
# reason. None until a page sends the first one, which is how a page knows to
# hand over what its browser held.
ARRANGE_FILE = os.path.join(os.path.dirname(LINKS_FILE), "arrangement.json")


def _load_arrangement():
    try:
        with open(ARRANGE_FILE) as f:
            return tidy(json.load(f))
    except (OSError, ValueError):
        return None


def tidy(body):
    """groups, layout and scales from what a page sent, or None if it is no arrangement."""
    if not isinstance(body, dict):
        return None
    groups = [g for g in body.get("groups") or [] if isinstance(g, dict) and isinstance(g.get("id"), str)]
    layout = body.get("layout")
    scales = body.get("scales")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e7
    return {
        "groups": groups[:200],
        # cards place themselves through the cards, so only windows are kept here
        "layout": {k: v for k, v in (layout.items() if isinstance(layout, dict) else ())
                   if isinstance(v, list) and len(v) == 2 and all(map(num, v)) and not k.startswith("link:")},
        "scales": {k: v for k, v in (scales.items() if isinstance(scales, dict) else ()) if num(v)},
    }


_arrange = _load_arrangement()
_arrange_lock = threading.Lock()


def arrangement():
    with _arrange_lock:
        return _arrange


def set_arrangement(body):
    """Last write wins. None, and why, if it is no arrangement."""
    global _arrange
    new = tidy(body)
    if not new:
        return None
    with _arrange_lock:
        _arrange = new
        try:
            os.makedirs(os.path.dirname(ARRANGE_FILE), exist_ok=True)
            with open(ARRANGE_FILE + ".tmp", "w") as f:
                json.dump(new, f)
            os.replace(ARRANGE_FILE + ".tmp", ARRANGE_FILE)
        except OSError:
            pass                        # still held, just not past a restart
    return new


CARD_PLACE = ("x", "y", "w", "h")


def placed(body):
    """Where a card sits and how big it is, from what a page sent: numbers only."""
    return {k: round(body[k]) for k in CARD_PLACE
            if isinstance(body.get(k), (int, float)) and not isinstance(body[k], bool)
            and abs(body[k]) < 1e7}


def send_link(url=None, title=None, path=None, image=None, keep=None, tool=None, folder=None, origin="api",
              term=None, cwd=None, note=False):
    """A card for the board: a web page (url), a markdown file (path), a
    picture (image: a path or an http(s) URL), a note (note: markdown typed
    on the card) or a button for one of a project's tools (tool, by name, in
    folder). None, and why, if it won't do.
    A tool card holds the name only: what it runs is looked up when pressed,
    so an edit to the script, or to .winlist-tools, is what runs next.
    keep is a card a browser held from before the board lived here: taken as
    it was, file or no file, with its place. origin is "page" when a page
    added it by hand; anything else is "api": sent from outside, to the Inbox.
    term (a WINLIST_TERM id) and cwd (a folder) say where it came from, so a
    page can put it beside that terminal, or in the group of that folder."""
    title = (title or "").strip()
    if keep:
        kind = next((k for k in ("image", "path", "url") if isinstance(keep.get(k), str) and keep[k]), None)
        if not kind:
            return None, "give a url, a path to a text file, or an image"
        card = {kind: keep[kind], "title": title or keep[kind]}
        card.update(placed(keep))
    elif note:
        card = {"note": True, "text": "", "title": title or "Note"}
    elif tool:
        tools, err = project_tools(folder or "")
        if err:
            return None, err
        found = next((t for t in tools if t["name"] == tool), None)
        if not found:
            return None, "no tool %s in %s" % (tool, folder)
        card = {"tool": tool, "dir": os.path.expanduser(folder), "about": found["about"],
                "title": title or tool}
    elif image:
        if not re.match(r"https?://[^/\s]+", image):
            image, _, err = image_file(image)
            if err:
                return None, err
        card = {"image": image, "title": title or image.rstrip("/").split("/")[-1]}
    elif path:
        doc, err = read_doc(path)
        if err:
            return None, err
        card = {"path": doc["path"], "title": title or doc["name"]}
    elif re.match(r"https?://[^/\s]+", url or ""):
        card = {"url": url, "title": title or fetch_title(url) or url.split("/")[2]}
    else:
        return None, "give a url, a path to a markdown file, or an image"
    with _links_lock:
        link = dict(card, id="%x" % time.time_ns(), origin="page" if origin == "page" else "api")
        for k, v in (("term", term), ("cwd", cwd)):
            if isinstance(v, str) and 0 < len(v) <= 4096:
                link[k] = v
        _links.append(link)
        _save_links()
    return link, None


def change_link(lid, body):
    """A card moved or resized on some page, or a note typed in; body None takes it off the board."""
    with _links_lock:
        link = next((l for l in _links if l["id"] == lid), None)
        if not link:
            return None
        if body is None:
            _links.remove(link)
        else:
            link.update(placed(body))
            if link.get("note") and isinstance(body.get("text"), str):
                link["text"] = body["text"][:200000]
        _save_links()
        return link


# A window that wants you — Claude finished in it — is pinged from outside, by
# a hook, and stays pinged until some page has seen it looked at. Kept here so
# every browser shows the same pings; in memory only, a restart forgets them.
_pings = {}                             # window id -> when it was pinged
_pings_lock = threading.Lock()


def ping(wid, on=True):
    """Ping a window, or with on=False let it be. False if the id is not one we use."""
    if not isinstance(wid, str) or not (wid.startswith("web:") or WIN_ID.match(wid)):
        return False
    wid = wid if wid.startswith("web:") else wid.lower()
    with _pings_lock:
        if on:
            _pings[wid] = time.time()
        else:
            _pings.pop(wid, None)
    return True


def pinged():
    with _pings_lock:
        return sorted(_pings)


# What Claude Code is doing in a window — working, waiting on you, or done —
# is reported by the same hook, one call per event, and the latest wins. Like
# pings, in memory only.
CLAUDE_STATES = ("working", "waiting", "done")
CLAUDE_STALE = 30 * 60                  # a "working" this old lost its Stop: let it go
_claude = {}                            # window id -> (state, when)
_claude_lock = threading.Lock()


def claude_state(wid, state):
    """Note what Claude is doing in a window. False if the id or state is not one we use."""
    if state not in CLAUDE_STATES or not isinstance(wid, str) \
            or not (wid.startswith("web:") or WIN_ID.match(wid)):
        return False
    wid = wid if wid.startswith("web:") else wid.lower()
    with _claude_lock:
        _claude[wid] = (state, time.time())
    return True


def claude_states(live):
    """{window id: {state, at}} for windows still there, minus a stale 'working'."""
    now = time.time()
    with _claude_lock:
        for wid, (state, at) in list(_claude.items()):
            if wid not in live or (state == "working" and now - at > CLAUDE_STALE):
                del _claude[wid]
        return {wid: {"state": st, "at": at} for wid, (st, at) in _claude.items()}


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

# The page itself is winlist/page/: index.html, style.css and app.js, served
# from disk as they stand, so an edit there shows on the next reload without
# restarting anything. index.html carries the two blanks filled in per port.
PAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page")


# ---- server ---------------------------------------------------------------


def same_page(origin, host, named=False):
    """Whether a request that changes something came from this page.

    Any site open in the browser can post to localhost, and the answer being
    unreadable to it does not matter when the post itself starts a terminal
    running whatever it was told. So a request from a page must come from this
    one: same host and port, and that host a loopback name or a bare address —
    never a domain, which could be made to point here after the page loaded.
    """
    if not origin and not named:
        return True                     # curl, and anything else without a page
    if origin and origin.split("//", 1)[-1].split("/")[0] != host:
        return False
    name = host[:host.find("]") + 1] if host.startswith("[") else host.rsplit(":", 1)[0]
    return name in ("127.0.0.1", "localhost", "[::1]") or bool(
        re.fullmatch(r"[\d.]+|\[[0-9a-fA-F:.]+\]", name))


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

    # Every file the page is made of, and nothing else: only these names are
    # ever served, and only from these two directories next to this script.
    # The libraries never change under a running page; the page's own files
    # are asked for afresh on each load, so an edit to one is a reload away.
    FILES = {
        "vendor": ({"xterm.js": "application/javascript", "xterm.css": "text/css",
                    "marked.min.js": "application/javascript"}, "public, max-age=86400"),
        "page": ({"app.js": "application/javascript", "style.css": "text/css"}, "no-cache"),
    }

    def _file(self, folder, name):
        kinds, cache = self.FILES[folder]
        kind = kinds.get(name)
        if not kind:
            return self._send(json.dumps({"error": "not found"}), code=404)
        here = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder)
        try:
            with open(os.path.join(here, name), "rb") as f:
                body = f.read()
        except OSError:
            return self._send(json.dumps({"error": "%s/%s is missing" % (folder, name)}), code=404)
        self._send(body, kind + "; charset=utf-8", cache=cache)

    def do_GET(self):
        folder, _, name = self.path.lstrip("/").partition("/")
        if folder in self.FILES:
            return self._file(folder, name.split("?")[0])
        m = re.fullmatch(r"/api/terminals/(\d{1,9})/scrollback(?:\?.*)?", self.path)
        if m:
            # what a terminal said is private: only this page, by a loopback name
            if not same_page(self.headers.get("Origin"), self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            out = scrollback(m.group(1))
            if out is None:
                return self._send(json.dumps({"error": "nothing saved"}), code=404)
            return self._send(out, "application/octet-stream", cache="no-store")
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
        elif self.path.startswith("/api/file?"):
            # a page under any other name could be a site pointed here to read
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            doc, err = read_doc(q.get("path", [""])[0], q.get("since", [None])[0])
            self._send(json.dumps(doc or {"error": err}), code=200 if doc else 404)
        elif self.path.startswith("/api/dir?"):
            # a group's folder is only worth keeping if a terminal can start there
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            path = os.path.expanduser(q.get("path", [""])[0])
            if os.path.isdir(path):
                return self._send(json.dumps({"ok": True, "path": path}))
            self._send(json.dumps({"error": "no such folder"}), code=404)
        elif self.path.startswith("/api/tools?"):
            # the commands come back to be run, so only this page may ask
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            tools, err = project_tools(q.get("dir", [""])[0])
            self._send(json.dumps({"tools": tools} if tools is not None else {"error": err}),
                       code=200 if tools is not None else 404)
        elif self.path.startswith("/api/image?"):
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            path, kind, err = image_file(q.get("path", [""])[0])
            if err:
                return self._send(json.dumps({"error": err}), code=404)
            try:
                with open(path, "rb") as f:
                    body = f.read()
            except OSError as e:
                return self._send(json.dumps({"error": e.strerror}), code=404)
            # an SVG is a document that can run script if opened as a page
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/ghstate?"):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            self._send(json.dumps(gh_state(q.get("url", [""])[0])))
        elif self.path in ("/", "/index.html"):
            port = self.server.server_address[1]
            try:
                with open(os.path.join(PAGE_DIR, "index.html"), encoding="utf-8") as f:
                    page = f.read()
            except OSError:
                return self._send(json.dumps({"error": "page/index.html is missing"}), code=404)
            page = (page.replace("__TITLE__", page_title(port))
                        .replace("_PORT_", ("%d" % port).ljust(6)[:6]))
            self._send(page, "text/html; charset=utf-8", cache="no-cache")
        else:
            self._send(json.dumps({"error": "not found"}), code=404)

    def _guard(self):
        if same_page(self.headers.get("Origin"), self.headers.get("Host", "")):
            return True
        self._send(json.dumps({"error": "cross-origin requests are refused"}), code=403)
        return False

    def do_POST(self):
        if not self._guard():
            return
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
        if self.path.startswith("/api/usage"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(min(n, 256 * 1024)) or b"[]")
            except (ValueError, json.JSONDecodeError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            return self._send(json.dumps({"kept": log_usage(body)}))
        if self.path.startswith("/api/ping"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            if not isinstance(body, dict) or not ping(body.get("window")):
                return self._send(json.dumps({"error": "give a window id"}), code=400)
            return self._send(json.dumps({"ok": True}))
        if self.path.startswith("/api/claude"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(min(n, 4096)) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            if not isinstance(body, dict) or not claude_state(body.get("window"), body.get("state")):
                return self._send(json.dumps({"error": "give a window id and a state"}), code=400)
            term_session(body.get("window"), body.get("session"))
            return self._send(json.dumps({"ok": True}))
        if self.path.startswith("/api/links"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            link, err = send_link(body.get("url"), body.get("title"), body.get("path"),
                                  body.get("image"), body.get("keep"), body.get("tool"), body.get("dir"),
                                  "page" if body.get("from") == "page" or body.get("keep") else "api",
                                  body.get("term"), body.get("cwd"), body.get("note") is True)
            if not link:
                return self._send(json.dumps({"error": err}), code=400)
            return self._send(json.dumps(link), code=201)
        return self._send(json.dumps({"error": "not found"}), code=404)

    def _card(self, body):
        lid = self.path[len("/api/links/"):].split("?")[0]
        link = change_link(lid, body)
        if not link:
            return self._send(json.dumps({"error": "no such card"}), code=404)
        self._send(json.dumps(link))

    def do_PUT(self):
        if not self._guard():
            return
        if self.path.split("?")[0] != "/api/arrangement":
            return self._send(json.dumps({"error": "not found"}), code=404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(json.dumps({"error": "bad request"}), code=400)
        new = set_arrangement(body)
        if not new:
            return self._send(json.dumps({"error": "bad request"}), code=400)
        self._send(json.dumps(new))

    def do_PATCH(self):
        if not self._guard():
            return
        terms = self.path.startswith("/api/terminals/")
        if not terms and not self.path.startswith("/api/links/"):
            return self._send(json.dumps({"error": "not found"}), code=404)
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(json.dumps({"error": "bad request"}), code=400)
        if not isinstance(body, dict):
            return self._send(json.dumps({"error": "bad request"}), code=400)
        if terms:
            sid = self.path[len("/api/terminals/"):].split("?")[0]
            ok = change_term(sid, body)
            return self._send(json.dumps({"ok": ok}), code=200 if ok else 404)
        self._card(body)

    def do_DELETE(self):
        if not self._guard():
            return
        if self.path.startswith("/api/links/"):
            return self._card(None)
        if self.path.startswith("/api/ping/"):
            ping(urllib.parse.unquote(self.path[len("/api/ping/"):].split("?")[0]), on=False)
            return self._send(json.dumps({"ok": True}))
        if not self.path.startswith("/api/terminals/"):
            return self._send(json.dumps({"error": "not found"}), code=404)
        sid = self.path[len("/api/terminals/"):].split("?")[0]
        change_term(sid, None)              # shut on purpose: not offered back
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


def relaunch(srv):
    """Replace this process with a fresh run of the same command line.

    The listening socket is closed first so the new process can bind the same
    port; the terminal server is a process of its own and is found again.
    """
    srv.server_close()
    cooked()
    argv = [a for a in sys.argv[1:] if a != "--open"]   # the page is already open
    os.execv(sys.executable, [sys.executable, os.path.abspath(sys.argv[0])] + argv)


_cooked = None   # the terminal's settings before we took single keys from it


def cooked():
    """Give the terminal back as it was found."""
    global _cooked
    if _cooked is not None:
        termios.tcsetattr(0, termios.TCSADRAIN, _cooked)
        _cooked = None


def watch_keys(srv):
    """`r` in the terminal winlist runs in restarts it, so Ctrl-C and run again
    is one key. Only when stdin is a terminal; Ctrl-C still works as ever."""
    global _cooked
    if not sys.stdin.isatty():
        return
    _cooked = termios.tcgetattr(0)
    tty.setcbreak(0)

    def read():
        while True:
            key = os.read(0, 1)
            if not key:
                return
            if key == b"r":
                relaunch(srv)

    threading.Thread(target=read, daemon=True).start()


# ---- as a service ---------------------------------------------------------

UNIT = "winlist.service"
UNIT_PATH = os.path.expanduser("~/.config/systemd/user/" + UNIT)

# KillMode=process: stopping the service ends this process only, so the
# terminal server it started stays up with your shells in it, as it does when
# a run by hand is restarted. It needs the desktop: X for the windows, the
# session's DISPLAY, which the user manager has once GNOME has started.
UNIT_TEXT = """[Unit]
Description=winlist: open windows by workspace, on %(url)s
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=%(cmd)s
Restart=on-failure
RestartSec=3
KillMode=process

[Install]
WantedBy=graphical-session.target
"""


# ---- project tools: what a group's folder knows how to run -----------------

TOOLS_FILE = ".winlist-tools"
LEAD = re.compile(r"^#\s*\S+\s+[—-]+\s+(.+)$")   # "# dev-server.sh — what it does"


def script_about(path):
    """The one-line summary a script gives in its opening comment, if any."""
    try:
        with open(path, errors="replace") as f:
            for _, line in zip(range(12), f):
                m = LEAD.match(line.strip())
                if m:
                    return m.group(1).strip().rstrip(".")
    except OSError:
        pass
    return ""


def project_tools(folder):
    """[{name, about, argv}] for a project folder, or an error.

    Two sources, as the action selector reads them: executable scripts at the
    top of the folder's tmp/ (dev-server.sh, deploy.sh), and a .winlist-tools
    file of `Name: command` lines for anything else. Each runs in bash and
    leaves a shell behind, so Ctrl-C stops a server without losing its tile:
    the trap is a handler, not an ignore, so the tool itself still gets the
    Ctrl-C while bash lives on past it.
    """
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return None, "no such folder"
    shell = os.environ.get("SHELL", "/bin/bash")
    found = []

    def add(name, cmd, about):
        found.append({"name": name, "about": about, "cmd": cmd,
                      "argv": ["bash", "-c", "trap : INT\n%s\nexec %s -i" % (cmd, shlex.quote(shell))]})

    try:
        with open(os.path.join(folder, TOOLS_FILE)) as f:
            for line in f:
                line = line.strip()
                name, sep, cmd = line.partition(":")
                if line and not line.startswith("#") and sep and cmd.strip():
                    add(name.strip(), cmd.strip(), "from " + TOOLS_FILE)
    except OSError:
        pass
    tmp = os.path.join(folder, "tmp")
    try:
        names = sorted(os.listdir(tmp))
    except OSError:
        names = []
    for n in names:
        path = os.path.join(tmp, n)
        if n.endswith(".sh") and os.path.isfile(path) and os.access(path, os.X_OK):
            add(n[:-3].replace("-", " ").replace("_", " ").capitalize(),
                "./tmp/" + shlex.quote(n), script_about(path))
    return found, None


def systemctl(*args):
    out = subprocess.run(("systemctl", "--user") + args, capture_output=True, text=True)
    return out.returncode == 0, (out.stderr or out.stdout).strip()


def service_active():
    return systemctl("is-active", "--quiet", UNIT)[0]


def install(argv, url):
    """Write the unit, with the flags this was run with, and start it now and
    with every session from here on."""
    cmd = [sys.executable, "-u", os.path.abspath(__file__)] + argv
    os.makedirs(os.path.dirname(UNIT_PATH), exist_ok=True)
    with open(UNIT_PATH, "w") as f:
        f.write(UNIT_TEXT % {"url": url, "cmd": " ".join(map(shlex.quote, cmd))})
    systemctl("daemon-reload")
    ok, msg = systemctl("enable", "--now", UNIT)
    if not ok:
        sys.exit("could not start %s: %s" % (UNIT, msg))
    say("installed %s, serving %s" % (UNIT_PATH, url))
    say("one already running by hand holds the port: stop it, and the service takes over within seconds")
    say("systemctl --user restart|stop|status winlist · journalctl --user -u winlist -f")


def uninstall():
    if not os.path.exists(UNIT_PATH):
        return say("no %s to remove" % UNIT_PATH)
    systemctl("disable", "--now", UNIT)
    os.remove(UNIT_PATH)
    systemctl("daemon-reload")
    say("removed %s; run it by hand again, r to restart, Ctrl-C to stop" % UNIT)


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
    ap.add_argument("--install", action="store_true",
                    help="run as a systemd user service, with the other flags given here, "
                         "from now on and with every desktop session")
    ap.add_argument("--uninstall", action="store_true", help="stop and remove that service")
    args = ap.parse_args()
    if args.uninstall:
        return uninstall()
    if args.install:
        return install([a for a in sys.argv[1:] if a not in ("--install", "--open")],
                       f"http://{args.host}:{args.port}/")
    Handler.allow_focus = not args.no_focus
    SHOTS_ON = not args.no_screens
    SHOT_WIDTH = max(320, args.shot_width)
    PTY_ON = not args.no_terminals
    PTY_PORT = args.pty_port
    LOOK.update(xterm_look())
    url = f"http://{args.host}:{args.port}/"
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        # the common case: launched a second time while one is already serving
        if args.open:
            say(f"winlist is already serving {url} — {show_page(url, args.port)}")
            return
        if service_active():
            say(f"the winlist service is serving {url} — "
                f"systemctl --user restart winlist, or stop it to run one here")
        else:
            say(f"cannot listen on {args.host}:{args.port} ({e}) — "
                f"another winlist is probably already running")
        sys.exit(1)
    if SHOTS_ON:
        threading.Thread(target=keep_shots, daemon=True).start()
    if args.open:
        threading.Thread(target=show_page, args=(url, args.port), daemon=True).start()

    how = start_terminals(PTY_PORT) if PTY_ON else None
    say(f"winlist → {url}  (r to restart, Ctrl-C to stop)")
    if PTY_ON:
        say("terminals → :%d, %s" % (PTY_PORT, how or "not running: " + _pty_error))

    # being killed is the ordinary way a server ends, so SIGTERM comes in by the
    # same door as Ctrl-C
    def hang_up(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, hang_up)
    watch_keys(srv)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
        say("bye")
    finally:
        cooked()


if __name__ == "__main__":
    main()
