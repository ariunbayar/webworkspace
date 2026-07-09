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

Thumbnail cache
---

File thumbnails are rendered once and cached to disk at `THUMB_CACHE_DIR`
(default `/tmp/thumb_cache` inside the container). There is no size limit or
TTL — entries are only ever replaced or discarded, as follows:

- **A single thumbnail re-renders** when its cache key changes. The key is
  `path + mtime + THUMB_FONT_SIZE + THUMB_LINE_PAD + THUMB_STYLE`, so editing
  the file or changing any of those settings produces a new entry (the old one
  is left orphaned, not deleted).
- **The whole cache is cleared on container recreate.** `/tmp/thumb_cache` is
  not a volume, so `docker compose up --build` (or `up -d`) starts a fresh
  container with an empty cache. A `docker compose restart` keeps it.
- **Clear it manually** without a recreate:

      docker compose exec web rm -rf /tmp/thumb_cache

To persist the cache across recreates instead, mount `THUMB_CACHE_DIR` as a
volume.
