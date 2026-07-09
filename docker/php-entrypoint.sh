#!/bin/sh
# Boot redis, seed db 2 with a demo project + file boxes, then serve the PHP app.
# DataStoreRedis connects to 127.0.0.1:6379 db 2, so redis lives in this container.
set -e

redis-server --daemonize yes --save "" --appendonly no
for i in $(seq 1 20); do
    redis-cli -n 2 ping >/dev/null 2>&1 && break
    sleep 0.2
done

# project directory the file boxes read from (filenames below must exist there)
DIR="${DEMO_DIR:-/app/static/js}"
case "$DIR" in */) ;; *) DIR="$DIR/" ;; esac

# demo data (keys match the PHP Model scheme: <name>_ids, <name>_<id>, last_id)
redis-cli -n 2 set project_ids '[1]' >/dev/null
redis-cli -n 2 set project_1 "{\"top\":10,\"left\":10,\"width\":150,\"height\":200,\"isActive\":false,\"directory\":\"$DIR\",\"id\":1}" >/dev/null
redis-cli -n 2 set file_ids '[1,2,3]' >/dev/null
redis-cli -n 2 set file_1 '{"top":90,"left":60,"width":300,"height":240,"isActive":false,"filename":"main.js","id":1}' >/dev/null
redis-cli -n 2 set file_2 '{"top":90,"left":400,"width":300,"height":240,"isActive":false,"filename":"DrawingArea.js","id":2}' >/dev/null
redis-cli -n 2 set file_3 '{"top":90,"left":740,"width":300,"height":240,"isActive":false,"filename":"File.js","id":3}' >/dev/null
redis-cli -n 2 set last_id 3 >/dev/null

echo "seeded redis db 2; serving PHP app on :8081 (project dir: $DIR)"
exec php -S 0.0.0.0:8081 -t web web/index.php
