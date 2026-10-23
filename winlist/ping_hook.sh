#!/bin/sh
# Ping this window on the winlist board. Meant for a Claude Code Stop hook:
# it must never fail, block or print, wherever it runs.
cat >/dev/null 2>&1                     # the hook's JSON is not needed
id=
if [ -n "$WINLIST_TERM" ]; then
  id="web:$WINLIST_TERM"
elif [ -n "$WINDOWID" ]; then
  # xterm gives decimal; winlist's ids are xprop's: 0x, lower case, no padding
  id=$(printf '0x%x' "$WINDOWID" 2>/dev/null)
fi
[ -n "$id" ] && curl -s -m 1 localhost:8766/api/ping -d "{\"window\":\"$id\"}" >/dev/null 2>&1
exit 0
