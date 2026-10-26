#!/bin/sh
# What a winlist tile is, for Claude or anyone at a shell. A ref is what y
# copies on the board: wl:note:…, wl:term:…, wl:win:…, or the whole /api/what URL.
#   winlist_what.sh                     every tile there is, as ref and title
#   winlist_what.sh <ref>               what it is and how to get at it, as JSON
#   winlist_what.sh <ref> --set < file  a note's new text, from stdin
base=${WINLIST_URL:-http://localhost:8766}
[ -z "$1" ] && exec curl -s "$base/api/what"
ref=${1##*ref=}
if [ "$2" = "--set" ]; then
  case "$ref" in wl:note:*) ;; *) echo "only a note (wl:note:…) can be changed here" >&2; exit 2 ;; esac
  jq -Rs '{text: .}' | curl -s -X PATCH "$base/api/links/${ref##*:}" \
    -H 'Content-Type: application/json' --data-binary @-
else
  curl -s --get "$base/api/what" --data-urlencode "ref=$ref"
fi
