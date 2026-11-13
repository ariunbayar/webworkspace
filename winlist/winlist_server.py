#!/usr/bin/env python3
"""winlist — a browser board of terminals and cards, stdlib only.

Terminals started from the page (held by pty_server.py, drawn by xterm.js),
cards for pages, documents and pictures, groups, pings and what Claude is up
to in each terminal. The server does not look at the desktop at all.

Run:  python3 winlist_server.py           # then open http://localhost:8766
      python3 winlist_server.py --port N  # custom port
      python3 winlist_server.py --open      # and open the page in the browser (xdg-open)
      python3 winlist_server.py --install     # run it as a service from now on
      python3 winlist_server.py --uninstall   # back to running it by hand

In a terminal, r restarts it and Ctrl-C stops it. As a service it is a systemd
user unit, winlist.service, started with the desktop session and logging to the
journal: systemctl --user restart|stop|status winlist, journalctl --user -u winlist.

pty_server.py holds the terminals; this starts it when nobody has, as a process
of its own, so restarting this one leaves your shells where they were.
`pkill -f pty_server.py` ends them.

The terminals' look is read from ~/.Xresources with xrdb, which does ask the X
server; if there is none, they simply get the page's defaults.
"""
import argparse
import collections
import html
import http.client
import json
import os
import re
import shlex
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


PTY_PORT = 8767       # pty_server.py, if it is running: terminals of our own
PTY_ON = True
_pty_error = ""

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
    """Sessions from pty_server.py, shaped like tiles so the page can put them
    on its surface. They have no place of their own, so they start laid out left
    to right and wrapped at `across`, which is only where they start: drag one
    and it stays where you put it. `desktop` is the cell they report, always 0.
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
            "min": False,
            "x": x, "y": y,
            "w": wide, "h": high,
            "z": 10000 + i,
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


def sample():
    """Everything the page draws: our terminals, the cards, the groups, the pings."""
    windows = terminals(0, 1920)
    return {
        "captured": time.strftime("%H:%M:%S"),
        "windows": windows,
        # where the page dials for a terminal
        "started": STARTED,
        "pty": {"on": PTY_ON, "port": PTY_PORT, "cell": 0, "error": _pty_error},
        "look": LOOK,          # what your xterm looks like, for ours to match
        "links": board(),       # the cards on the board, the same in every browser
        "arrange": arrangement(),  # its groups and tile places; None until a page sends one
        "lost": lost_terms(),   # terminals a reboot took, for the page to offer back
        "pings": pinged(),      # terminals that want you, the same in every browser
        "claude": claude_states(windows),  # what Claude is up to in each
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


# a web address with nothing in it a request can't carry: a space or a control
# character got through the old prefix check and killed the request mid-way
WEB_URL = re.compile(r"https?://[^/\x00-\x20\x7f]+[^\x00-\x20\x7f]*")


def fetch_title(url):
    """What the page calls itself, if it will say without a login: else None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 winlist"})
        with urllib.request.urlopen(req, timeout=3) as r:
            if "html" not in r.headers.get("Content-Type", ""):
                return None
            head = r.read(65536).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except (OSError, ValueError, http.client.HTTPException):    # InvalidURL is one, not a ValueError
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


# A diff card shows what a PR changes. The head commit is asked for at most
# every 30 seconds, and the diff itself only when that commit has changed, so
# the page's polling costs GitHub next to nothing. Over a megabyte is cut.
_diffs = {}
DIFF_MAX = 1 << 20
PR_URL = r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)"


def _gh_run(args, timeout):
    out = subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=timeout)
    if out.returncode:
        raise ValueError((out.stderr.strip().splitlines() or ["gh failed"])[-1][:200])
    return out.stdout


def pr_diff(url, since=None):
    """A PR's files (with + and - counts), head sha and diff text; or {"error"}.
    With since (the sha the page has) and no change, only the sha is sent."""
    m = re.fullmatch(PR_URL, url or "")
    if not m:
        return {"error": "not a GitHub PR address"}
    hit = _diffs.get(url)
    if not hit or time.time() - hit[0] >= (30 if "error" not in hit[1] else 10):
        owner, repo, n = m.groups()
        repo_args = [n, "--repo", "%s/%s" % (owner, repo)]
        try:
            info = json.loads(_gh_run(["pr", "view"] + repo_args + ["--json", "headRefOid,files"], 15))
            sha = info["headRefOid"]
            if hit and hit[1].get("sha") == sha:
                answer = hit[1]
            else:
                raw = _gh_run(["pr", "diff"] + repo_args, 30).encode("utf-8", "replace")
                answer = {"sha": sha, "cut": len(raw) > DIFF_MAX,
                          "text": raw[:DIFF_MAX].decode("utf-8", "ignore"),
                          "files": [{"path": f.get("path"), "additions": f.get("additions", 0),
                                     "deletions": f.get("deletions", 0)} for f in info.get("files", [])]}
        except FileNotFoundError:
            answer = {"error": "gh is not installed"}
        except subprocess.TimeoutExpired:
            answer = {"error": "GitHub took too long"}
        except (ValueError, KeyError, TypeError) as e:
            answer = {"error": str(e) or "no answer from gh"}
        hit = _diffs[url] = (time.time(), answer)
    answer = hit[1]
    if since and answer.get("sha") == since:
        return {"sha": since, "same": True}
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



SKIP_DIRS = {"node_modules", "__pycache__", "venv", "site-packages"}


def find_file(name, size, mtime_ms, limit=3.0):
    """Where a file dropped from a file manager lives. The browser hands over
    only its name, size and time, so look for that file under home: hidden and
    bulky folders are skipped, and the search gives up after limit seconds.
    The paths that match, best first (none if it isn't there or is too deep)."""
    home, end, found = os.path.expanduser("~"), time.monotonic() + limit, []
    for top, dirs, files in os.walk(home):
        if time.monotonic() > end:
            break
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
        if name not in files:
            continue
        path = os.path.join(top, name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_size == size:
            found.append((abs(st.st_mtime * 1000 - mtime_ms), path))
    return [p for gap, p in sorted(found) if gap < 2000] or [p for gap, p in sorted(found)][:1]

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
              term=None, cwd=None, note=False, diff=None):
    """A card for the board: a web page (url), a markdown file (path), a
    picture (image: a path or an http(s) URL), a note (note: markdown typed
    on the card), a PR's changes (diff: the PR's address) or a button for one of a project's tools (tool, by name, in
    folder). None, and why, if it won't do.
    A tool card holds the name only: what it runs is looked up when pressed,
    so an edit to tmp/.winlist-tools.yml, or to what it runs, is what runs next.
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
    elif diff:
        m = re.fullmatch(PR_URL, diff)
        if not m:
            return None, "diff takes a GitHub PR address"
        card = {"diff": diff, "title": title or "Diff · PR #" + m.group(3)}
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
        if not WEB_URL.fullmatch(image):
            image, _, err = image_file(image)
            if err:
                return None, err
        card = {"image": image, "title": title or image.rstrip("/").split("/")[-1]}
    elif path:
        doc, err = read_doc(path)
        if err:
            return None, err
        card = {"path": doc["path"], "title": title or doc["name"]}
    elif WEB_URL.fullmatch(url or ""):
        card = {"url": url, "title": title or fetch_title(url) or url.split("/")[2]}
    elif re.match(r"https?:", url or ""):
        return None, "bad url: it has a space or a control character in it (encode it, e.g. %20)"
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


# A tile can be handed to Claude as a ref: wl:<kind>:<id>, where kind is note,
# doc, img, url, tool or diff for a card, term for a page terminal. Claude asks GET /api/what?ref=… and is told what is behind
# it and how to get at it: a file's path, a note's text and how to change it,
# a terminal's folder and saved output.
REF = re.compile(r"(?:.*[?&]ref=)?wl:([a-z]+):([0-9A-Za-z]{1,64})")


def card_kind(link):
    return next((k for k, v in (("note", "note"), ("path", "doc"), ("image", "img"), ("tool", "tool"),
                                ("diff", "diff")) if link.get(k)), "url")


def proc_of(pid):
    """What /proc says of a process: its folder and command line (None where it won't say)."""
    out = {"pid": pid or None, "cwd": None, "cmdline": None}
    if not pid:
        return out
    try:
        out["cwd"] = os.readlink("/proc/%d/cwd" % pid)
    except OSError:
        pass
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            out["cmdline"] = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
    except OSError:
        pass
    return out


def what(ref, base="http://localhost:8766"):
    """What a ref points at, as a dict, or None if there is no such tile (any more)."""
    m = REF.fullmatch((ref or "").strip())
    if not m:
        return None
    kind, key = m.groups()
    out = {"ref": "wl:%s:%s" % (kind, key)}
    if kind == "term":
        answer = pty("/sessions") if PTY_ON else None
        t = next((t for t in (answer or {}).get("sessions", []) if t.get("id") == key), None)
        if not t:
            return None
        with _terms_lock:
            known = dict(_terms.get(key, {}))
        out.update(kind="terminal", title=t.get("title", ""), running=t.get("running", ""),
                   cwd=t.get("cwd", ""), alive=t.get("alive", False), shell=proc_of(t.get("pid", 0)),
                   claude_session=known.get("session"), last_commands=_last_cmds(key),
                   saved_output=_term_file(key, ".out"),
                   read_output="curl -s %s/api/terminals/%s/scrollback" % (base, key))
        return out
    with _links_lock:
        link = next((dict(l) for l in _links if l["id"] == key), None)
    if not link:
        return None
    out.update(kind=card_kind(link), title=link.get("title", ""))
    for k in ("url", "path", "image", "tool", "dir", "about", "diff", "term", "cwd"):
        if link.get(k):
            out[k] = link[k]
    if link.get("note"):
        out["text"] = link.get("text", "")
        # a note lives in links.json, not a file: it is changed through the server,
        # and every page shows the new text at its next look
        out["change"] = ("curl -s -X PATCH %s/api/links/%s -H 'Content-Type: application/json' "
                         "-d \"$(jq -Rs '{text: .}' < NEW_TEXT_FILE)\"" % (base, key))
        out["or"] = "%s %s --set < NEW_TEXT_FILE" % (os.path.join(HERE, "winlist_what.sh"), out["ref"])
    elif link.get("path"):
        out["note"] = "a file on disk: read or edit it there; the card follows saves"
    return out


def refs():
    """Every tile there is now, as ref and title: the cards, and the page's terminals."""
    with _links_lock:
        out = [{"ref": "wl:%s:%s" % (card_kind(l), l["id"]), "title": l.get("title", "")} for l in _links]
    for t in ((pty("/sessions") if PTY_ON else None) or {}).get("sessions", []):
        if t.get("alive"):
            out.append({"ref": "wl:term:" + t["id"], "title": t.get("title") or t.get("running") or "shell"})
    return out

# A window that wants you — Claude finished in it — is pinged from outside, by
# a hook, and stays pinged until some page has seen it looked at. Kept here so
# every browser shows the same pings, and in pings.json so a restart keeps
# them. A week-old one is let go: its window is likely long gone.
PINGS_FILE = os.path.join(os.path.dirname(LINKS_FILE), "pings.json")
PING_KEEP = 7 * 24 * 3600
_pings_lock = threading.Lock()


def _load_pings():
    try:
        with open(PINGS_FILE) as f:
            old = time.time() - PING_KEEP
            return {k: v for k, v in json.load(f).items()
                    if isinstance(v, (int, float)) and v > old}
    except (OSError, ValueError, AttributeError):
        return {}


_pings = _load_pings()                  # window id -> when it was pinged


def _save_pings():
    """Called holding _pings_lock."""
    try:
        os.makedirs(os.path.dirname(PINGS_FILE), exist_ok=True)
        with open(PINGS_FILE + ".tmp", "w") as f:
            json.dump(_pings, f)
        os.replace(PINGS_FILE + ".tmp", PINGS_FILE)
    except OSError:
        pass                            # still pinged, just not past a restart


def ping(wid, on=True):
    """Ping a window, or with on=False let it be. False if the id is not one we use."""
    if not isinstance(wid, str) or not wid.startswith("web:"):
        return False
    with _pings_lock:
        if on:
            _pings[wid] = time.time()
        elif _pings.pop(wid, None) is None:
            return True
        _save_pings()
    return True


def pinged():
    with _pings_lock:
        return sorted(_pings)


# What Claude Code is doing in a window — working, waiting on you, or done —
# is reported by the same hook, one call per event, and the latest wins. In
# memory only.
CLAUDE_STATES = ("working", "waiting", "done")
CLAUDE_STALE = 30 * 60                  # a "working" this old lost its Stop: let it go
CLAUDE_GONE = 5                         # s with no claude left in a page terminal: it quit
_claude = {}                            # window id -> (state, when)
_claude_missing = {}                    # page window id -> when claude was first not found
_claude_lock = threading.Lock()


def claude_state(wid, state):
    """Note what Claude is doing in a window. False if the id or state is not one we use."""
    if state not in CLAUDE_STATES + ("gone",) or not isinstance(wid, str) or not wid.startswith("web:"):
        return False
    with _claude_lock:
        if state == "gone":             # SessionEnd: Claude quit, the chip goes with it
            _claude.pop(wid, None)
        else:
            _claude[wid] = (state, time.time())
    return True


def claude_under(pids):
    """The terminal pids, of those given, that are claude or have a claude process
    somewhere below them (a terminal started as claude has it on top). One pass over /proc. Claude running a tool puts bash or node in the
    foreground, so the foreground program alone would say it had gone."""
    kids = collections.defaultdict(list)
    comm = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % d) as f:
                st = f.read()
        except OSError:
            continue
        r = st.rfind(")")
        comm[int(d)] = st[st.find("(") + 1:r]
        kids[int(st[r + 2:].split()[1])].append(int(d))
    found = set()
    for top in pids:
        todo = [top]
        while todo:
            p = todo.pop()
            if comm.get(p) == "claude":
                found.add(top)
                break
            todo.extend(kids.get(p, ()))
    return found


def claude_states(windows):
    """{window id: {state, at}} for windows still there, minus a stale 'working',
    and minus a page terminal whose Claude has quit (none left under its shell for
    CLAUDE_GONE seconds)."""
    now = time.time()
    live = {w["id"] for w in windows}
    shells = {w["id"]: w.get("pid") for w in windows if w["id"].startswith("web:") and w.get("pid")}
    with _claude_lock:
        watch = {wid: shells[wid] for wid in _claude if wid in shells}
    with_claude = claude_under(set(watch.values())) if watch else set()
    with _claude_lock:
        for wid, pid in watch.items():
            if pid in with_claude:
                _claude_missing.pop(wid, None)
            elif now - _claude_missing.setdefault(wid, now) >= CLAUDE_GONE:
                _claude.pop(wid, None)
                _claude_missing.pop(wid, None)
        for wid in list(_claude_missing):
            if wid not in _claude:
                del _claude_missing[wid]
        for wid, (state, at) in list(_claude.items()):
            if wid not in live or (state == "working" and now - at > CLAUDE_STALE):
                del _claude[wid]
        return {wid: {"state": st, "at": at} for wid, (st, at) in _claude.items()}


PAGE_TITLE = "Open windows"
DEFAULT_PORT = 8766


def page_title(port):
    """Off the default port the title carries it, so one winlist's page is
    never mistaken for another's."""
    return PAGE_TITLE if port == DEFAULT_PORT else "%s :%d" % (PAGE_TITLE, port)


def show_page(url):
    """Open the page in the desktop's browser, and let go of it."""
    try:
        subprocess.Popen(["xdg-open", url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


# ---- page -----------------------------------------------------------------

# The page itself is winlist/page/: index.html, style.css and app.js, served
# from disk as they stand, so an edit there shows on the next reload without
# restarting anything. index.html carries the two blanks filled in per port.
HERE = os.path.dirname(os.path.abspath(__file__))
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
            self._send(json.dumps(sample()))
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
        elif self.path.split("?")[0] == "/api/what":
            # what a tile handed to Claude is: note text and paths, so only by a loopback name
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            ref = q.get("ref", [""])[0]
            if not ref:
                return self._send(json.dumps({"tiles": refs()}))
            found = what(ref, "http://" + self.headers.get("Host", "localhost:8766"))
            if not found:
                return self._send(json.dumps({"ref": ref, "gone": True,
                                              "error": "no such tile, or it has been closed"}), code=404)
            self._send(json.dumps(found))
        elif self.path.startswith("/api/find?"):
            # a file dropped from a file manager comes without its path
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                name, size, mtime = q["name"][0], int(q["size"][0]), float(q.get("mtime", ["0"])[0])
            except (KeyError, ValueError):
                return self._send(json.dumps({"error": "bad request"}), code=400)
            if "/" in name or name in ("", ".", ".."):
                return self._send(json.dumps({"error": "bad name"}), code=400)
            self._send(json.dumps({"paths": find_file(name, size, mtime)}))
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
        elif self.path.startswith("/api/diff?"):
            if not same_page(None, self.headers.get("Host", ""), named=True):
                return self._send(json.dumps({"error": "refused"}), code=403)
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            self._send(json.dumps(pr_diff(q.get("url", [""])[0], q.get("since", [""])[0])))
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
                                  body.get("term"), body.get("cwd"), body.get("note") is True, body.get("diff"))
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
# a run by hand is restarted. It starts with the desktop session so that
# --open and the terminals' look (xrdb) find its DISPLAY, which the user
# manager has once GNOME has started.
UNIT_TEXT = """[Unit]
Description=winlist: terminals and cards on a browser board, on %(url)s
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

TOOLS_FILE = os.path.join("tmp", ".winlist-tools.yml")   # in the project's ignored tmp/


def project_tools(folder):
    """[{name, about, argv}] for a project folder, or an error.

    One source: the folder's tmp/.winlist-tools.yml, a YAML list of tools,
    each `name` and `run` (a command, or a script over several lines with
    `run: |`), an optional one-line `about`, and `confirm: true` for one that
    takes a second press to run. Nothing else is guessed, so the
    file is the whole list, in its order; no file is no tools. Each runs in bash and
    leaves a shell behind, so Ctrl-C stops a server without losing its tile:
    the trap is a handler, not an ignore, so the tool itself still gets the
    Ctrl-C while bash lives on past it.
    """
    folder = os.path.expanduser(folder)
    if not os.path.isdir(folder):
        return None, "no such folder"
    try:
        with open(os.path.join(folder, TOOLS_FILE)) as f:
            text = f.read()
    except OSError:
        return [], None
    try:
        import yaml
    except ImportError:
        return None, "reading %s needs PyYAML (pip install pyyaml)" % TOOLS_FILE
    try:
        items = yaml.safe_load(text) or []
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        return None, "%s: not valid YAML%s" % (TOOLS_FILE, " (line %d)" % (mark.line + 1) if mark else "")
    if not isinstance(items, list):
        return None, "%s: expected a list of tools (- name: … run: …)" % TOOLS_FILE
    shell = os.environ.get("SHELL", "/bin/bash")
    found = []
    for i, t in enumerate(items, 1):
        if not isinstance(t, dict) or not str(t.get("name") or "").strip() or not str(t.get("run") or "").strip():
            return None, "%s: tool %d needs a name and a run" % (TOOLS_FILE, i)
        cmd = str(t["run"]).strip()
        about = str(t.get("about") or "").strip() or cmd.splitlines()[0]
        found.append({"name": str(t["name"]).strip(), "about": about, "cmd": cmd,
                      "confirm": t.get("confirm") is True,
                      "argv": ["bash", "-c", "trap : INT\n%s\nexec %s -i" % (cmd, shlex.quote(shell))]})
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
    global PTY_PORT, PTY_ON
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="show the page in the browser once serving")
    ap.add_argument("--pty-port", type=int, default=PTY_PORT, metavar="N",
                    help="port for the terminals (default %d); one already "
                         "listening there is used as it stands" % PTY_PORT)
    ap.add_argument("--no-terminals", action="store_true",
                    help="do not hold terminals at all")
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
    PTY_ON = not args.no_terminals
    PTY_PORT = args.pty_port
    LOOK.update(xterm_look())
    url = f"http://{args.host}:{args.port}/"
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        # the common case: launched a second time while one is already serving
        if args.open:
            say(f"winlist is already serving {url}")
            show_page(url)
            return
        if service_active():
            say(f"the winlist service is serving {url} — "
                f"systemctl --user restart winlist, or stop it to run one here")
        else:
            say(f"cannot listen on {args.host}:{args.port} ({e}) — "
                f"another winlist is probably already running")
        sys.exit(1)
    if args.open:
        threading.Thread(target=show_page, args=(url,), daemon=True).start()

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
