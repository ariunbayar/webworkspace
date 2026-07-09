Web workspace
===

Execute server with following command:

    cd web; php -S 127.0.0.1:8081 index.php

And go to http://127.0.0.1:8081/

Resource monitor
---

Live local CPU / memory / load dashboard, stdlib only (no redis, no pip installs):

    python3 resmon_server.py

Then open http://127.0.0.1:8765/ — polls /proc every 2s and shows CPU, memory,
load average, and top processes by CPU. Use `--port N` / `--host H` to change binding.

Run with Docker (demo)
---

Runs the Flask app (`runserver.py`) with a co-located redis and seeded demo
data — no local PHP, redis, or Python setup needed:

    cp .env.example .env        # optional
    docker compose up --build

Then open http://127.0.0.1:8000/ — the workspace loads with a few sample file
boxes. Change `DEMO_DIR` in `.env` to seed a different sample directory.
