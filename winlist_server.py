#!/usr/bin/env python3
"""Open windows by workspace — live web dashboard, stdlib only.

Lists every visible window grouped into the workspace grid the desktop actually
uses, and focuses one on click or keyboard pick.

Run:  python3 winlist_server.py           # then open http://localhost:8766
      python3 winlist_server.py --port N  # custom port
      python3 winlist_server.py --open      # and bring the page up in the browser
      python3 winlist_server.py --no-focus  # read-only, refuse focus requests

X11 only: it reads EWMH properties via xprop/xdotool.
"""
import argparse
import json
import re
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


# ---- sampling -------------------------------------------------------------


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

    # one xdotool call for every geometry, in client-list order
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
  .right { margin-left:auto; font-variant-numeric:tabular-nums }
  .here { margin-left:auto; font-size:9.5px; text-transform:uppercase; letter-spacing:.05em;
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
  .map { position:relative; margin:6px; border:1px solid var(--line); border-radius:4px;
         background:var(--empty); overflow:hidden }
  .rect { position:absolute; border-radius:2px; overflow:hidden; padding:1px 3px; font-size:9px;
          line-height:1.2; color:#fff; text-shadow:0 1px 1px rgba(0,0,0,.5); cursor:pointer;
          border:1px solid rgba(0,0,0,.28) }
  .rect.off { opacity:.25 }
  .blank { flex:1; min-height:32px }
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
    </div>
    <span class="keys"><kbd>↑↓←→</kbd>/<kbd>hjkl</kbd> pick · <kbd>Enter</kbd> focus ·
      <kbd>/</kbd> filter · <kbd>Esc</kbd> clear</span>
  </div>
  <div class="grid" id="grid"></div>
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

let data = null, view = "list", sel = null, failures = 0;

$('#view').onclick = e => { const b = e.target.closest('button'); if (!b) return;
  view = b.dataset.v;
  [...$('#view').children].forEach(x => x.setAttribute('aria-pressed', x === b));
  render(); };
$('#q').addEventListener('input', () => { sel = null; render(); });

async function poll() {
  try {
    const r = await fetch('/api/windows');
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
  const match = visible(), grid = $('#grid');
  grid.style.gridTemplateColumns = `repeat(${data.grid.cols}, minmax(0,1fr))`;
  grid.innerHTML = "";
  // one cell per workspace, row-major, empty ones included so positions hold still
  for (let i = 0; i < data.grid.cols * data.grid.rows; i++) {
    const ws = onWorkspace(i);
    const card = document.createElement('section');
    card.className = 'ws' + (ws.length ? '' : ' empty') + (i === data.current ? ' current' : '');
    const row = Math.floor(i / data.grid.cols) + 1, col = i % data.grid.cols + 1;
    card.innerHTML = `<div class="wshead"><span class="wsnum">${i + 1}</span>
      <span class="rc">r${row}c${col}</span>
      ${i === data.current ? '<span class="here">here</span>'
        : `<span class="right">${ws.length || ''}</span>`}</div>`;
    if (!ws.length) { card.innerHTML += '<div class="blank"></div>'; grid.append(card); continue; }
    if (view === 'map') {
      card.innerHTML += `<div class="map" style="padding-bottom:${data.screen.h / data.screen.w * 100}%"></div>`;
      const map = card.querySelector('.map');
      [...ws].reverse().forEach(w => {          // bottom of the stack painted first
        const r = document.createElement('div');
        r.className = 'rect' + (match(w) ? '' : ' off') + (w.id === sel ? ' sel' : '');
        r.style.cssText = `left:${Math.max(0, w.x) / data.screen.w * 100}%;
          top:${Math.max(0, w.y) / data.screen.h * 100}%;
          width:${Math.min(w.w, data.screen.w) / data.screen.w * 100}%;
          height:${Math.min(w.h, data.screen.h) / data.screen.h * 100}%;
          background:${colorOf(w.app)};${w.focused ? 'z-index:9' : ''}`;
        r.textContent = w.title;
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
  const hits = data.windows.filter(match), q = $('#q').value.trim();
  $('#stat').textContent = `${hits.length}${q ? " of " + data.windows.length : ""} windows · `
    + `${data.grid.cols}×${data.grid.rows} workspaces · ${new Set(data.windows.map(w => w.desktop)).size} in use`;
  $('#ts').innerHTML = failures ? `<span class="stale">disconnected — retrying</span>`
    : `updated ${data.captured}`;
  $('#foot').innerHTML = `Grid from ${data.grid.source} `
    + `(<code>${data.grid.cols}</code> × <code>${data.grid.rows}</code>, row-major); `
    + `windows placed by <code>_NET_WM_DESKTOP</code>, app resolved from WM_CLASS plus the `
    + `process running inside the window. Click a window or press <kbd>Enter</kbd> to focus it.`;
}

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

function move(dx, dy) {
  const match = visible();
  const pick = data.windows.filter(match);
  if (!pick.length) return;
  const cur = selected();
  if (!cur) { sel = pick[0].id; return render(); }

  if (dy && !dx) {                       // within a workspace, then on to the next one
    const here = ordered(cur.desktop).filter(match);
    const at = here.findIndex(w => w.id === cur.id);
    if (at + dy >= 0 && at + dy < here.length) { sel = here[at + dy].id; return render(); }
  }
  const cols = data.grid.cols, cells = cols * data.grid.rows;
  let i = cur.desktop;
  for (let step = 0; step < cells; step++) {   // walk the grid to the next occupied cell
    i += dx + dy * cols;
    if (i < 0) i += cells;
    if (i >= cells) i -= cells;
    const there = ordered(i).filter(match);
    if (there.length) { sel = there[dy > 0 ? 0 : there.length - 1].id; return render(); }
  }
}

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') {
    if (e.key === 'Escape') { e.target.value = ''; e.target.blur(); sel = null; render(); }
    return;
  }
  const k = e.key;
  if (k === '/') { e.preventDefault(); $('#q').focus(); return; }
  if (k === 'Escape') { $('#q').value = ''; sel = null; return render(); }
  if (k === 'Enter' || k === ' ') { const w = selected(); if (w) { e.preventDefault(); activate(w.id); } return; }
  const moves = { ArrowUp: [0, -1], k: [0, -1], ArrowDown: [0, 1], j: [0, 1],
                  ArrowLeft: [-1, 0], h: [-1, 0], ArrowRight: [1, 0], l: [1, 0] };
  if (moves[k]) { e.preventDefault(); move(...moves[k]); }
});

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

    def _send(self, body, ctype="application/json", code=200):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/windows"):
            self._send(json.dumps(sample()))
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
        self._send(json.dumps({"ok": ok, "msg": msg}), code=200 if ok else 400)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="show the page in the browser once serving")
    ap.add_argument("--no-focus", action="store_true", help="serve read-only, refuse focus requests")
    args = ap.parse_args()
    Handler.allow_focus = not args.no_focus
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
    if args.open:
        threading.Thread(target=show_page, args=(url, args.port), daemon=True).start()
    print(f"winlist → {url}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
