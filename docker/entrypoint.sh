#!/bin/sh
# Boot redis, seed demo data, then serve the Flask app.
set -e

# in-memory redis is fine for a throwaway demo
redis-server --daemonize yes --save "" --appendonly no

# wait until redis (db 2) answers before seeding
for i in $(seq 1 20); do
    redis-cli -n 2 ping >/dev/null 2>&1 && break
    sleep 0.3
done

python /app/docker/seed_demo.py

# flask run binds 0.0.0.0 without editing runserver.py's __main__ block
exec flask run --no-reload --host 0.0.0.0 --port "${PORT:-8000}"
