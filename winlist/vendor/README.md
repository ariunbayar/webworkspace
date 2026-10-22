Vendored
===

`xterm.js` and `xterm.css` are xterm.js 6.0.0, taken unmodified from

    https://cdnjs.cloudflare.com/ajax/libs/xterm/6.0.0/xterm.js
    https://cdnjs.cloudflare.com/ajax/libs/xterm/6.0.0/xterm.css

MIT licensed; the notice is at the top of each file. They live here rather than
on a CDN because `winlist_server.py` serves a page that has to work with no
network at all, and because a terminal emulator is not something to fetch from
somewhere else at the moment you need it.

To move to another version, drop the two files in and change nothing else —
`winlist_server.py` serves whatever is here, by name.

`marked.min.js` is marked 12.0.2, also unmodified, from

    https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js

It turns a markdown file on the surface into HTML. The page drops any raw HTML
in the file and keeps only http(s) and mailto links, since whatever it shows
sits next to terminals it can type into.
