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

    python3 winlist_server.py --open

Serves http://127.0.0.1:8766/ and brings the page up in the browser — raising
the window that already shows it rather than opening another tab, so launching
this twice costs nothing. Drop `--open` to just serve. The page polls every 2s.

Each window is a tile, labelled with the app it belongs to — resolved from
`WM_CLASS` plus the process running inside the window, so a terminal running
`claude` or `vim` says so instead of "XTerm".

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
and the slider zoom, dragging the background carries the whole surface with it,
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

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.
