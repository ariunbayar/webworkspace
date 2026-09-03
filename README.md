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

    python3 winlist_server.py

Then open http://127.0.0.1:8766/ — polls every 2s. Each workspace is a cell of
the grid (read from the wsmatrix extension's `num-columns`/`num-rows`, falling
back to `_NET_DESKTOP_LAYOUT`), empty workspaces included so cells stay put.
Windows are labelled by app, resolved from `WM_CLASS` plus the process running
inside the window — a terminal running `claude` or `vim` says so instead of
"XTerm". "Titles" lists window titles per workspace; "Map" draws each workspace
to scale with the real window rectangles.

Click a window — or pick one with the arrow keys / `hjkl` and press Enter — to
focus it, which also switches to its workspace. `/` filters, `Esc` clears.
Run with `--no-focus` to serve read-only, `--port N` to change the port.

X11 only (uses `xprop`/`xdotool`).

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.
