"""Seed redis (db 2) with a demo project + a few file boxes so the workspace
renders something on first load. Keys match what runserver.py reads:
  project_38   -> {'directory': ...}   (thumbnail() hard-codes id 38)
  file_ids     -> [1, 2, 3]
  file_<id>    -> box geometry + filename
"""
import json
import os

import redis

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
# thumbnail.py always lexes with JavascriptLexer, so demo files must be JS to
# render cleanly (non-JS produces Token.Error and 500s).
DEMO_DIR = os.environ.get("DEMO_DIR", "/app/static/js")
if not DEMO_DIR.endswith("/"):
    DEMO_DIR += "/"  # thumbnail() does proj_dir + filename

r = redis.StrictRedis(host=REDIS_HOST, port=6379, db=2, decode_responses=True)

project = {
    "id": 38,
    "directory": DEMO_DIR,
    "top": 10, "left": 10, "width": 200, "height": 150,
    "isActive": False,
}

files = [
    {"id": 1, "filename": "main.js",        "left": 60,  "top": 90, "width": 300, "height": 240, "isActive": False},
    {"id": 2, "filename": "DrawingArea.js", "left": 400, "top": 90, "width": 300, "height": 240, "isActive": False},
    {"id": 3, "filename": "File.js",        "left": 740, "top": 90, "width": 300, "height": 240, "isActive": False},
]

r.set("project_38", json.dumps(project))
r.set("project_ids", json.dumps([38]))
r.set("file_ids", json.dumps([f["id"] for f in files]))
for f in files:
    r.set("file_%s" % f["id"], json.dumps(f))
r.set("last_id", max(f["id"] for f in files))

print("seeded %d files from %s" % (len(files), DEMO_DIR))
