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

Live list of every visible window, arranged in the same workspace grid the
desktop uses, stdlib only:

    python3 winlist_server.py --open

Serves http://127.0.0.1:8766/ and brings the page up in the browser — raising
the window that already shows it rather than opening another tab, so launching
this twice costs nothing. Drop `--open` to just serve. The page polls every 2s.

Each workspace is a cell of the grid (read from the wsmatrix extension's
`num-columns`/`num-rows`, falling back to `_NET_DESKTOP_LAYOUT`), empty
workspaces included so cells stay put. Within a workspace, windows are grouped
under the app they belong to, resolved from `WM_CLASS` plus the process running
inside the window — a terminal running `claude` or `vim` says so instead of
"XTerm". "Titles" lists window titles per workspace; "Map" draws each workspace
to scale with the real window rectangles.

The map also photographs your workspaces. X only hands out the pixels actually
on the glass, so a window on another workspace cannot be captured — only the
workspace in front of you can. So each cell keeps the last photo taken of that
workspace and says how long ago that was: cells fill in as you move around, and
clicking a window to jump somewhere gets that workspace photographed once you
land. Window outlines stay on top of the photo, and filtering greys out the
windows that do not match. Needs ImageMagick's `convert` (`apt install
imagemagick`); without it the map stays a plain diagram and says so. Grabbing
only runs while a browser actually has the map open — and `--no-screens` turns
it off entirely.

Click a window — or pick one with the arrow keys / `hjkl` and press Enter — to
focus it, which also switches to its workspace. `/` filters, `Esc` clears.
Run with `--no-focus` to serve read-only, `--no-screens` to never photograph
the screen, `--port N` to change the port.

X11 only (uses `xprop`/`xdotool`, plus `xwd` and `convert` for the photos).

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.
