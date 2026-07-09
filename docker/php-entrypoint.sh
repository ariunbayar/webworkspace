#!/bin/sh
# Boot redis, seed db 2 with a demo project + file boxes, then serve the PHP app.
# DataStoreRedis connects to 127.0.0.1:6379 db 2, so redis lives in this container.
set -e

redis-server --daemonize yes --save "" --appendonly no
for i in $(seq 1 20); do
    redis-cli -n 2 ping >/dev/null 2>&1 && break
    sleep 0.2
done

# seed db 2 with a box per project source file (scans DEMO_DIR)
php /app/docker/php-seed.php

echo "serving PHP app on :8081"
exec php -S 0.0.0.0:8081 -t web web/index.php
