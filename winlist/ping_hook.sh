#!/bin/sh
# Tell the winlist board what Claude is doing in this window. Meant for Claude
# Code hooks: it must never fail, block or print, wherever it runs.
# The event comes in the hook's JSON: Stop also pings (as it always has), the
# rest only set the state shown in the tile's caption.
in=$(cat 2>/dev/null)
ev=$(printf %s "$in" | sed -n 's/.*"hook_event_name" *: *"\([A-Za-z]*\)".*/\1/p' | head -n 1)
sess=$(printf %s "$in" | sed -n 's/.*"session_id" *: *"\([A-Za-z0-9-]*\)".*/\1/p' | head -n 1)
id=
if [ -n "$WINLIST_TERM" ]; then
  id="web:$WINLIST_TERM"
elif [ -n "$WINDOWID" ]; then
  # xterm gives decimal; winlist's ids are xprop's: 0x, lower case, no padding
  id=$(printf '0x%x' "$WINDOWID" 2>/dev/null)
fi
[ -n "$id" ] || exit 0
case "$ev" in
  UserPromptSubmit|PreToolUse|PostToolUse) st=working ;;
  Notification)                            # the idle reminder is not a question
    case "$in" in *idle_prompt*) exit 0 ;; esac
    st=waiting ;;
  Stop|"") st=done ;;                      # no event: an old Stop hook
  SessionEnd) st=gone ;;                   # Claude quit: the chip goes
  *) exit 0 ;;
esac
[ "$st" = done ] && curl -s -m 1 localhost:8766/api/ping -d "{\"window\":\"$id\"}" >/dev/null 2>&1
[ -n "$sess" ] && sess=",\"session\":\"$sess\""
curl -s -m 1 localhost:8766/api/claude -d "{\"window\":\"$id\",\"state\":\"$st\"$sess}" >/dev/null 2>&1
exit 0
