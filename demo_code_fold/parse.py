from __future__ import print_function

import sys
import io

from pygments import lex
from pygments.token import Token
from pygments.lexers.javascript import JavascriptLexer

from PIL import Image
from PIL.ImageColor import getrgb


base03  = getrgb('#002b36')  # background tones
base02  = getrgb('#073642')  # background tones
base01  = getrgb('#586e75')
base00  = getrgb('#657b83')
base0   = getrgb('#839496')
base1   = getrgb('#93a1a1')
base2   = getrgb('#eee8d5')  # background tones
base3   = getrgb('#fdf6e3')  # background tones
yellow  = getrgb('#b58900')
orange  = getrgb('#cb4b16')
red     = getrgb('#dc322f')
magenta = getrgb('#d33682')
violet  = getrgb('#6c71c4')
blue    = getrgb('#268bd2')
cyan    = getrgb('#2aa198')
# green   = getrgb('#859900')  # original by solarized
green   = getrgb('#719e07')  # experimental by solarized


colors = {
    'Token.Keyword.Declaration': {
        'var'      : yellow,
        'function' : yellow,
    },
    # TODO mark XXX and TODO
    'Token.Comment.Single': base01,
    'Token.Keyword.Constant': {
        'null'  : yellow,
        'false' : cyan,
        'true'  : cyan,
    },
    'Token.Text'                 : None,  # usually newline or space
    'Token.Literal.String.Single': cyan,
    'Token.Literal.String.Double': cyan,
    'Token.Keyword': {
        'this'   : red,
        'break'  : green,
        'else'   : green,
        'if'     : green,
        'new'    : green,
        'return' : green,
        'while'  : green,
    },
    'Token.Literal.Number.Integer': cyan,
    'Token.Name.Builtin': {
        'window': cyan,
    },
    'Token.Operator': {
        '>'   : green,
        '||'  : green,
        '&&'  : green,
        '===' : green,
        '=='  : green,
        '='   : green,
        '!'   : green,
        '+'   : green,
        '-'   : green,
        ':'   : base0,  # no definition by vim yet
    },
    'Token.Punctuation': {
        '.': base0,
        '{': blue,  # TODO rainbow colors
        '}': blue,  # TODO rainbow colors
        '[': blue,  # TODO rainbow colors
        ']': blue,  # TODO rainbow colors
        ',': base0,  # TODO rainbow colors following the bracket
        '(': base0,  # TODO rainbow colors
        ')': base0,  # TODO rainbow colors
        ';': base0,
    },
    'Token.Name.Other': base0,
}


def generate_image(lexer_result, rows, columns, output_file):
    char_width, char_height = (2, 4)
    image_size = (columns * char_width, rows * char_height)

    img = Image.new("RGBA", image_size, base03)

    column = 1
    row = 1
    for token, value in lexer_result:
        token_name = str(token)
        if token_name not in colors:
            raise Exception("Undefined %s -> %s" % (token_name, repr(value)))
            continue

        if isinstance(colors[token_name], dict):
            if value not in colors[token_name]:
                raise Exception("Undefined %s -> %s" % (token_name, repr(value)))
                continue
            color = colors[str(token)][value]
        else:
            color = colors[str(token)]

        print(value, end='')

        for char in value:
            if char == '\n':
                column = 0
                row += 1
            elif char == ' ':
                pass
            else:
                if token == Token.Text:
                    raise Exception("Token.Text must only contain newline or space")
                if char not in ' ':
                    x = (column - 1) * char_width
                    y = (row - 1) * char_height
                    img.putpixel((x, y), color)
                    img.putpixel((x+1, y), color)
                    img.putpixel((x, y+1), color)
                    img.putpixel((x+1, y+1), color)
                    img.putpixel((x, y+2), color)
                    img.putpixel((x+1, y+2), color)
                    img.putpixel((x, y+3), color)
                    img.putpixel((x+1, y+3), color)

            column += 1

    img.save(output_file)


if __name__ == '__main__':
    filename = sys.argv[1]

    feed = ""
    rows = 0
    columns = 0
    with io.open(filename, encoding='utf-8') as f:
        for line in f:
            rows += 1
            columns = max(len(line), columns)
            feed += line

    lexer_result = lex(feed, JavascriptLexer())
    generate_image(lexer_result, rows, columns, "output.png")
