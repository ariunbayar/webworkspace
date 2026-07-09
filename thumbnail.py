"""Render a source file to a small syntax-highlighted PNG for the workspace boxes.

Uses Pygments' ImageFormatter at a small font size, so each character is a real
(pixelized) glyph rather than a solid block, while the whole image stays small.
Lexer is chosen by filename (any language); colors come from a Pygments style.
Results are cached to disk keyed by path + mtime + font size + style.

Needs a TTF font on the system (the Docker image installs fonts-dejavu-core).
"""
import hashlib
import io
import os

from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import guess_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound


# small font => pixelized glyphs; override with THUMB_FONT_SIZE
FONT_SIZE = int(os.environ.get("THUMB_FONT_SIZE", 7))
FONT_NAME = os.environ.get("THUMB_FONT_NAME", "DejaVu Sans Mono")
STYLE = os.environ.get("THUMB_STYLE", "monokai")
CACHE_DIR = os.environ.get("THUMB_CACHE_DIR", "/tmp/thumb_cache")

FORMATTER = ImageFormatter(
    style=STYLE,
    font_name=FONT_NAME,
    font_size=FONT_SIZE,
    line_numbers=False,
    line_pad=0,
)


def _render(filename):
    with io.open(filename, encoding="utf-8", errors="replace") as f:
        code = f.read()

    try:
        lexer = guess_lexer_for_filename(filename, code)
    except ClassNotFound:
        lexer = TextLexer()

    return highlight(code, lexer, FORMATTER)


def generate_thumbnail(filename):
    try:
        mtime = os.path.getmtime(filename)
    except OSError:
        mtime = 0

    seed = "%s:%s:fs%s:%s" % (filename, mtime, FONT_SIZE, STYLE)
    path = os.path.join(CACHE_DIR, hashlib.md5(seed.encode()).hexdigest() + ".png")

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
