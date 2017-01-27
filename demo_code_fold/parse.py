import sys
import io
import re

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
    'TODO': magenta,
    'XXX': magenta,
    'newline': red,
    'Token.Keyword.Declaration': {
        'var'      : yellow,
        'function' : yellow,
    },
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
        'switch' : green,
        'case'   : green,
        'default': green,
    },
    'Token.Literal.Number.Integer': cyan,
    'Token.Name.Builtin': {
        'window': cyan,
        'Math'  : cyan,
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
        '/'   : green,
        '*'   : green,
        ':'   : base0,  # no definition by vim yet
    },
    'Token.Punctuation': {
        '.': base0,
        '{': base0,  # TODO rainbow colors
        '}': base0,  # TODO rainbow colors
        '[': base0,  # TODO rainbow colors
        ']': base0,  # TODO rainbow colors
        ',': base0,  # TODO rainbow colors following the bracket
        '(': base0,  # TODO rainbow colors
        ')': base0,  # TODO rainbow colors
        ';': base0,
    },
    'Token.Name.Other': {
        'console': cyan,
        '': base0,
    },
}

char_to_pixels = {
    #   x 01010101
    #   y 00112233
    #     v v v v
    '!' : " # # #  ",
    '\"': "##      ",
    '#' : "######  ",
    '$' : "######  ",
    '%' : "  ####  ",
    '&' : "# ####  ",
    '\'': "#       ",
    '(' : " ## #  #",
    ')' : "#  # ## ",
    '*' : "####    ",
    '+' : "  ###   ",
    ',' : "     #  ",
    '-' : "  ##    ",
    '.' : "     #  ",
    '/' : " # ## # ",
    '0' : "######  ",
    '1' : " # ###  ",
    '2' : "## ###  ",
    '3' : "## ###  ",
    '4' : " ### #  ",
    '5' : "######  ",
    '6' : "# ####  ",
    '7' : "## ##   ",
    '8' : "######  ",
    '9' : "#### #  ",
    ':' : " #   #  ",
    ';' : " #   ## ",
    '<' : "   ###  ",
    '=' : "  ##    ",
    '>' : "  # ##  ",
    '?' : "#####   ",
    '@' : " #####  ",
    'A' : " #####  ",
    'B' : "### ##  ",
    'C' : "### ##  ",
    'D' : "######  ",
    'E' : "### ##  ",
    'F' : "#####   ",
    'G' : "######  ",
    'H' : "######  ",
    'I' : "##  ##  ",
    'J' : " # ###  ",
    'K' : "### ##  ",
    'L' : "# # ##  ",
    'M' : "######  ",
    'N' : "######  ",
    'O' : "######  ",
    'P' : "#####   ",
    'Q' : "######  ",
    'R' : "######  ",
    'S' : "######  ",
    'T' : "##  #   ",
    'U' : "######  ",
    'V' : "#####   ",
    'W' : "######  ",
    'X' : "##  ##  ",
    'Y' : "##  #   ",
    'Z' : "##  ##  ",
    '[' : "### # ##",
    '\\': "# #  # #",
    ']' : "## # ###",
    '^' : "##      ",
    '_' : "      ##",
    '`' : "#  #    ",
    'a' : "  ####  ",
    'b' : "# ####  ",
    'c' : "  ####  ",
    'd' : " #####  ",
    'e' : "  ####  ",
    'f' : " ####   ",
    'g' : "  ######",
    'h' : "# ####  ",
    'i' : " # ###  ",
    'j' : " #   ###",
    'k' : "# ####  ",
    'l' : "# #  #  ",
    'm' : "  ####  ",
    'n' : "  ####  ",
    'o' : "  ####  ",
    'p' : "  ##### ",
    'q' : "  #### #",
    'r' : "  ###   ",
    's' : "  ####  ",
    't' : "# ###   ",
    'u' : "  ####  ",
    'v' : "  ###   ",
    'w' : "   ###  ",
    'x' : "   ##   ",
    'y' : "  ######",
    'z' : "  ####  ",
    '{' : " ##### #",
    '|' : "# # # # ",
    '}' : "# ##### ",
    '~' : "  ##    ",
}


def rgb2hex(rgb):
    return '%02x%02x%02x' % rgb


def generate_image(lexer_result, rows, columns, output_file, is_test=False):
    char_width, char_height = (2, 4)
    image_size = (columns * char_width, rows * char_height)

    img = Image.new("RGBA", image_size, base03)
    if is_test == True:
        yield (-1, -1, '#' + rgb2hex(base03))

    column = 1
    row = 1
    for token, value in lexer_result:
        token_name = str(token)
        if token_name not in colors:
            raise Exception("Undefined %s -> %s" % (token_name, repr(value)))
            continue

        if isinstance(colors[token_name], dict):
            if value in colors[token_name]:
                color = colors[token_name][value]
            elif '' in colors[token_name]:
                color = colors[token_name]['']
            else:
                raise Exception("Undefined %s -> %s" % (token_name, repr(value)))
                continue
        else:
            color = colors[token_name]

        special_colors = {}
        if token == Token.Comment.Single:
            for m in re.finditer('TODO|XXX', value):
                if m.group() == 'TODO':
                    i = m.start()
                    special_colors[i] = colors['TODO']
                    special_colors[i + 1] = colors['TODO']
                    special_colors[i + 2] = colors['TODO']
                    special_colors[i + 3] = colors['TODO']
                if m.group() == 'XXX':
                    i = m.start()
                    special_colors[i] = colors['XXX']
                    special_colors[i + 1] = colors['XXX']
                    special_colors[i + 2] = colors['XXX']

        if token == Token.Literal.String.Single or token == Token.Literal.String.Double:
            for m in re.finditer('\\\\n', value):
                i = m.start()
                special_colors[i] = colors['newline']
                special_colors[i + 1] = colors['newline']

        char_color = color
        for i, char in enumerate(value):
            if char == '\n':
                column = 0
                row += 1
            elif char == ' ':
                pass
            else:
                if token == Token.Text:
                    raise Exception("Token.Text must only contain newline or space")
                if token in [Token.Comment.Single, Token.Literal.String.Single, Token.Literal.String.Double]:
                    if i in special_colors:
                        char_color = special_colors[i]
                    else:
                        char_color = color
                if char not in ' ':
                    x = (column - 1) * char_width
                    y = (row - 1) * char_height
                    if char in char_to_pixels:
                        pixels = char_to_pixels[char]
                        for i, p in enumerate(pixels):
                            if p == '#':
                                img.putpixel((x + (i % 2), y + int(i / 2)), char_color)
                    else:
                        print(char)

                    if is_test == True:
                        yield (row, column, '#' + rgb2hex(char_color))

            column += 1

    img.save(output_file)


def parse_file(filename):
    feed = ""
    rows = 0
    columns = 0
    with io.open(filename, encoding='utf-8') as f:
        for line in f:
            rows += 1
            columns = max(len(line), columns)
            feed += line

    lexer_result = lex(feed, JavascriptLexer())

    return lexer_result, rows, columns


if __name__ == '__main__':
    filename = sys.argv[1]

    lexer_result, rows, columns = parse_file(filename)
    generator = generate_image(lexer_result, rows, columns, "output.png")

    for row, column, color in generator:
        pass
