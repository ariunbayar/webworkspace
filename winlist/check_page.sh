#!/usr/bin/env bash
# Parse the page's scripts the way the browser will, so a slip that would leave
# it blank fails here instead: a syntax error, or a name declared twice in one
# module (PR #85 shipped a duplicate function, and the whole page went).
# Run:  winlist/check_page.sh      (also run by .github/workflows/page-check.yml)
set -euo pipefail
cd "$(dirname "$0")/page"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
fail=0
# node only parses a file as a module when it is named .mjs
for f in *.js; do
  cp "$f" "$tmp/${f%.js}.mjs"
  node --check "$tmp/${f%.js}.mjs" || { echo "page/$f: does not parse as a module"; fail=1; }
done
# the inline <script> blocks in index.html are classic scripts
python3 -I - index.html "$tmp" <<'PY' || fail=1
import re, subprocess, sys
html = open(sys.argv[1]).read()
bad = 0
for n, m in enumerate(re.finditer(r'<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>', html, re.S)):
    path = "%s/inline%d.%s" % (sys.argv[2], n, "mjs" if 'type="module"' in m.group(1) else "js")
    open(path, "w").write(m.group(2))
    if subprocess.run(["node", "--check", path]).returncode:
        print("page/index.html: inline script %d does not parse" % n); bad = 1
sys.exit(bad)
PY
[ $fail = 0 ] && echo "page: all scripts parse"
exit $fail
