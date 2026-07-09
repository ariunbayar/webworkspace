"""Seed redis (db 2) so the workspace displays this project's own source files.

Walks DEMO_DIR (default the repo root, /app), keeps text/source files, and lays
them out as a grid of boxes. Keys match what runserver.py reads:
  project_38   -> {'directory': ...}   (thumbnail() hard-codes id 38)
  file_ids     -> [1, 2, ...]
  file_<id>    -> box geometry + filename (relative to the project directory)
"""
import json
import os

import redis

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
ROOT = os.environ.get("DEMO_DIR", "/app").rstrip("/")

SOURCE_EXT = {".py", ".php", ".js", ".css", ".html", ".sh", ".yml", ".yaml", ".txt", ".md"}
EXTRA_NAMES = {".env.example", ".dockerignore", ".gitignore"}
SKIP_DIRS = {".git", "__pycache__", "libs", "node_modules"}
VENDOR_PREFIX = ("createjs-", "easeljs-", "tweenjs-", "underscore", "backbone", "jquery")

# grid layout
COLS = 6
BOX_W, BOX_H, GAP_X, GAP_Y, X0, Y0 = 240, 300, 40, 60, 60, 80


def is_source(name):
    if name in EXTRA_NAMES or name.startswith("Dockerfile"):
        return True
    if name.endswith(".min.js") or name.startswith(VENDOR_PREFIX):
        return False
    return os.path.splitext(name)[1] in SOURCE_EXT


def collect(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if is_source(name):
                found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(found)


files = collect(ROOT)
r = redis.StrictRedis(host=REDIS_HOST, port=6379, db=2, decode_responses=True)

r.set("project_38", json.dumps({
    "id": 38, "directory": ROOT + "/",
    "top": 10, "left": 10, "width": 200, "height": 150, "isActive": False,
}))
r.set("project_ids", json.dumps([38]))

ids = []
for i, rel in enumerate(files):
    fid = i + 1
    ids.append(fid)
    col, row = i % COLS, i // COLS
    r.set("file_%s" % fid, json.dumps({
        "id": fid, "filename": rel,
        "left": X0 + col * (BOX_W + GAP_X),
        "top": Y0 + row * (BOX_H + GAP_Y),
        "width": BOX_W, "height": BOX_H, "isActive": False,
    }))
r.set("file_ids", json.dumps(ids))
r.set("last_id", len(files))

print("seeded %d project files from %s" % (len(files), ROOT))
