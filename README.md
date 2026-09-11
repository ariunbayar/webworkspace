Web workspace
===

Execute server with following command:

    cd web; php -S 127.0.0.1:8081 index.php

And go to http://127.0.0.1:8081/

Run with Docker (demo)
---

The PHP app (file browser, project management, open-in-editor) runs as the
`php` compose service — PHP 7.4 + phpredis + a co-located redis (db 2), seeded
with demo boxes. No local PHP or redis setup needed:

    cp .env.example .env        # optional
    docker compose up --build

Then open http://127.0.0.1:8081/ (override with `PHP_PORT`). Press `?` in the
app for keybindings. Change `PHP_DEMO_DIR` in `.env` to seed a different
sample directory.

Open windows
---

Every window there is on one surface, laid out however you like, stdlib only:

    python3 winlist/winlist_server.py --open

Serves http://127.0.0.1:8766/ and brings the page up in the browser — raising
the window that already shows it rather than opening another tab, so launching
this twice costs nothing. Drop `--open` to just serve. The page polls every 2s.

Each window is a tile, labelled with the app it belongs to — resolved from
`WM_CLASS` plus the process running inside the window, so a terminal running
`claude` or `vim` says so instead of "XTerm".

Terminals look like the ones you already configured: the server reads the plain
`XTerm` class out of your X resources at startup — palette, font and face size,
cursor blink, scrollback, and the geometry a new one opens at — and the page
uses them. A named class like `font-cozette*` is a profile you ask for by name,
not the default you get by typing `xterm`, so it is left alone. Nothing there,
or no X at all, and it falls back to its own colours.

**New terminal** (or `t`) puts a shell of the page's own on the same surface,
in a cell of its own past the last workspace. It is a real terminal, drawn by
xterm.js and wired to `pty_server.py`: click into it and type. Drag it by its
title bar rather than anywhere on it — the rest of it is for typing into — and
`✕` closes it. Everything else about a tile still holds: it scales with the
surface, so zoom out and the terminal goes small with the photographs, zoom in
and you can read it.

A shell that exits leaves its tile behind, greyed, with its last words still
in it and the reason it went in the title bar. **new shell** there starts
another one in its place — the same size, the same directory, the same spot on
the surface, since that is what pointing at that tile meant — and `✕` clears it
away. Nothing else needs restarting: not the page, not the server. Left alone,
it goes by itself after ten minutes.

Pull the bottom-right corner to resize it. The count of characters is what
changes, not the picture: the terminal is told, the kernel is told, and the
program running in it gets a SIGWINCH and redraws while you are still pulling,
exactly as it would in a window you were dragging. The corner reads out the
size as you go, and the handle stays the same size however far you zoom out, so
there is always something to grab.

Once a terminal is big enough to read, the wheel over it scrolls its scrollback
rather than zooming the surface — it is a terminal at that point, not a tile.
Zoomed further out than anyone could read, it goes back to being a tile and the
wheel means zoom again.

The tiles show real pixels. X only hands out what is actually on the glass, so
a window on another workspace cannot be photographed — only the workspace in
front of you can. So the last photo taken of each workspace is kept and its
windows cut out of it: tiles fill in as you move around, and clicking a window
to jump somewhere gets that workspace photographed once you land. Needs
ImageMagick's `convert` (`apt install imagemagick`); without it tiles stay
plain colours and the page says so. Grabbing only runs while a browser actually
has the page open — and `--no-screens` turns it off entirely. `--shot-width PX`
sets the resolution (1280 by default; a bigger number costs bytes, not time —
the capture is dominated by reading the screen, not by scaling it).

Each tile is cut out of its workspace's photo. Windows start out grouped by the workspace they live on,
those groups packed into a squarish block — the desktop's own grid is not drawn
and not used, since it is far taller than any browser window and mostly empty —
and from there you drag each window wherever you want it. **Dragging moves the tile and nothing else**: the window
manager is never touched, so this is a place to arrange your windows as you
think about them rather than as the desktop has them. The arrangement is
remembered in the browser (per window), "Reset layout" puts it back, the wheel
and the slider zoom, dragging the background with the mouse carries the whole
surface with it,
and clicking a window still focuses it for real. The surface is placed rather
than scrolled, so it has no edges: you can drag it as far as you like, and zoom
runs free from 2% to 400%. "Fit" brings everything back into view.

A photo is of a whole workspace, so cutting one window's rectangle out of it
also cuts out anything that was lying on top. The stacking order at the moment
of the shutter says exactly which parts those are, so they are struck out with
a hatch rather than passed off as that window's own content, and a window that
was completely buried says so instead of showing a picture of whatever was in
front of it. The window on top of a workspace always comes out whole.

It works the same under a finger: drag a window to move it, drag the background
to pan, and pinch to zoom — two fingers sliding pan as they pinch, and a pinch
that starts mid-drag leaves the window where it had got to. Zoom always happens
about a point, the mouse or the middle of the pinch, so whatever you are
looking at stays put instead of sliding off. Dashed boxes mark the workspaces the windows came from.

The `⤢` button (or `f`) hands the page the whole browser window — the heading,
the footer and the margins go, and the surface is pinned to the viewport so the
canvas is the window, the zoom still fitting until you work the slider or start
dragging tiles. It is a layout, not F11: the browser stays a browser.

"Architecture" (or `a`) draws the pieces and who talks to whom: the page, this
server, X, and the terminal server that will hold shells the page starts
itself. None of that plumbing shows on the surface, so it gets a picture.

Click a window — or pick one with the arrow keys / `hjkl` and press Enter — to
focus it, which also switches to its workspace; the arrow keys still walk the
workspaces the windows came from, in order. `/` filters, `Esc` clears (then
leaves the full window).
Run with `--no-focus` to serve read-only, `--no-screens` to never photograph
the screen, `--port N` to change the port.

X11 only (uses `xprop`/`xdotool`, plus `xwd` and `convert` for the photos).

Terminals
---

Shells the browser can hold on to, one pseudo-terminal each, stdlib only.
`winlist_server.py` runs this inside itself, so there is normally nothing to
start: the terminals come up with the page and go when it goes, and `pstree`
shows one process holding the shells rather than two programs to remember. Run
it on its own when you want it on its own:

    python3 winlist/pty_server.py

Serves http://127.0.0.1:8767/sessions. One already listening there is somebody
else's — `winlist_server.py` leaves it alone and uses it as it stands, rather
than taking over something it did not start and would then have to stop. A page cannot start a shell — it has no
way in — so this holds the terminals instead: it starts one on a PTY, streams
what it prints to whoever is attached, and writes back what they type. The
terminal lives here rather than in the tab, so a reload reattaches to the
session it left instead of killing it, and two tabs can watch the same one.

Because it owns them, it can say what X never could: the pid, the directory the
foreground program is sitting in, the name of that program, and the title the
program set for itself. No guessing from `WM_CLASS`.

A shell opened here is a new session, not a continuation of whatever started
the server, so the session markers some programs leave in the environment are
dropped on the way in. Without that, a Claude Code run inside one of these
terminals finds the marker its parent left, decides it is a subprocess rather
than a session of its own, and turns transcript saving off. Settings are kept —
only per-session plumbing goes.

    GET    /sessions              every session, and what is running in it
    POST   /sessions              start one: {"cwd", "argv", "cols", "rows"}
    POST   /sessions/<id>/resize  {"cols", "rows"}
    DELETE /sessions/<id>         hang it up — SIGHUP, then SIGKILL if it dawdles
    GET    /attach/<id>           websocket: binary frames carry terminal bytes
                                  both ways, text frames are JSON control messages

Each session keeps its last 256 KB of output, handed over the moment you
attach, so a terminal redraws itself instead of coming up blank. A session that
has ended stays listed for ten minutes and can still be attached to: it hands
over what it said and then closes, so its last words survive a reload rather
than only lasting as long as the tab that watched it die.

Handing out shells deserves some care, so: it listens on loopback and refuses
anything else unless you say `--allow-remote`, and it turns away handshakes
from any page that is not itself local — a WebSocket is not stopped by the
same-origin policy, so a site you happen to be reading could otherwise dial
this port. `--shell` picks what a session runs (default `$SHELL`),
`--max-sessions` caps how many at once.

    python3 winlist/pty_server_test.py

runs the whole thing against a server of its own on a free port: typing,
resizing, Ctrl-C, reattaching, two watchers on one terminal, and the refusals.

`winlist_server.py` draws them. It asks this server what exists, folds the
answer into the same window list as the real windows, and the page dials
`/attach` straight from the tab — so the bytes of a terminal never make the
detour through the window list. It degrades quietly: no terminal server, no
terminals, and the surface is just windows again.

Stopping it takes the shells with it, before it returns rather than on a timer
somebody might not wait for: each gets the SIGHUP that closing a terminal
window sends, a couple of seconds to go quietly, and then a signal it cannot
refuse. Being killed is the ordinary way a server ends, so SIGTERM comes in by
the same door as Ctrl-C. `--no-terminals` holds none at all.

The emulator is xterm.js 6.0.0, vendored in `vendor/` rather than fetched from
anywhere at runtime. A prompt full of Nerd Font glyphs needs a font that has
them; the page names `PowerlineSymbols` and a couple of others after its
workhorse, and the browser falls back per glyph.

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.
