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

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.
