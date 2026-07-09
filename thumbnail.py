"""Render a source file to a tiny "minimap" PNG for the workspace boxes.

Each character becomes a small colored block (like an editor minimap): not
readable, but shows the shape/color of the whole file. Colors come from a
Pygments *style* (style_for_token), so it works for any language and any
Pygments version — no hand-maintained token->color map. Results are cached to
disk keyed by path + mtime.
"""
import hashlib
import io
import os

from PIL import Image, ImageDraw
from pygments import lex
from pygments.lexers import guess_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound


CHAR_W, CHAR_H = 2, 3            # block size per character
TAB_WIDTH = 4
STYLE = get_style_by_name("monokai")
DEFAULT_FG = "888888"
CACHE_DIR = os.environ.get("THUMB_CACHE_DIR", "/tmp/thumb_cache")

_color_cache = {}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


BG_RGB = _hex_to_rgb(STYLE.background_color or "1e1e1e")


def _color_for(ttype):
    if ttype not in _color_cache:
        style = STYLE.style_for_token(ttype)
        _color_cache[ttype] = _hex_to_rgb(style.get("color") or DEFAULT_FG)
    return _color_cache[ttype]


def _render(filename):
    with io.open(filename, encoding="utf-8", errors="replace") as f:
        code = f.read().expandtabs(TAB_WIDTH)

    try:
        lexer = guess_lexer_for_filename(filename, code)
    except ClassNotFound:
        lexer = TextLexer()

    lines = code.split("\n")
    rows = max(1, len(lines))                      # full file height by default
    cols = max((len(line) for line in lines), default=1) or 1

    img = Image.new("RGB", (cols * CHAR_W, rows * CHAR_H), BG_RGB)
    draw = ImageDraw.Draw(img)

    col = row = 0
    for ttype, text in lex(code, lexer):
        color = _color_for(ttype)
        for ch in text:
            if ch == "\n":
                row, col = row + 1, 0
            elif ch == " ":
                col += 1
            else:
                x, y = col * CHAR_W, row * CHAR_H
                draw.rectangle([x, y, x + CHAR_W - 1, y + CHAR_H - 1], fill=color)
                col += 1

    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def generate_thumbnail(filename):
    try:
        mtime = os.path.getmtime(filename)
    except OSError:
        mtime = 0

    key = hashlib.md5(("%s:%s" % (filename, mtime)).encode()).hexdigest()
    path = os.path.join(CACHE_DIR, key + ".png")

    if os.path.exists(path):
        with open(path, "rb") as f:
            return io.BytesIO(f.read())

    data = _render(filename)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    except OSError:
        pass  # rendering still works without a cache

    return io.BytesIO(data)
