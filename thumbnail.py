"""Render a source file to a syntax-highlighted PNG for the workspace boxes.

Uses Pygments' ImageFormatter so any language works (lexer picked by filename)
and there's no hand-maintained token->pixel map to drift with new Pygments
releases. Requires a TTF font on the system (see the Docker image:
fontconfig + fonts-dejavu-core).
"""
import io

from pygments import highlight
from pygments.formatters import ImageFormatter
from pygments.lexers import guess_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound


FORMATTER = ImageFormatter(
    style="monokai",
    font_name="DejaVu Sans Mono",
    font_size=18,
    line_numbers=False,
)


def generate_thumbnail(filename):
    with io.open(filename, encoding="utf-8", errors="replace") as f:
        code = f.read()

    try:
        lexer = guess_lexer_for_filename(filename, code)
    except ClassNotFound:
        lexer = TextLexer()

    png_bytes = highlight(code, lexer, FORMATTER)
    return io.BytesIO(png_bytes)
