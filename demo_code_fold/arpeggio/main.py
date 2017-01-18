import io
from arpeggio import Optional, ZeroOrMore, EOF
from arpeggio import RegExMatch as _
from arpeggio import ParserPython

from generate_html import generate_html


def ws():
    return _(r'[\n\r\t ]*')

def line_comment():
    return '//', _(r'[^\n]*')

def type_integer():
    return _(r'\d+')

def type_float():
    return _(r'\d*\.\d+')

def naming():
    # Applies to function, variable and property names
    return _(r'[a-zA-Z_]\w*')

def this_scope():
    return 'this'

def obj():
    # object, variable, class, function
    return naming, ws, Optional('(', ws, ZeroOrMore(assignables, ws), ')')

def access():
    return '.', ws, obj

def object_access():
    return obj, ZeroOrMore(ws, '.', ws, obj)

def assignables():
    return [this_scope, type_float, type_integer, function, object_access]

def assignment():
    return naming, Optional(ws, '=', ws, assignables)

def declaration():
    return Optional('var'), ws, assignment, ws, ZeroOrMore(',', ws, assignment, ws), ';'

def function():
    return 'function', ws, Optional(naming, ws), '()', ws, '{', statements, '}'

def function_in_bracket():
    return '(', ws, function, ws, ZeroOrMore(access, ws), ');'

def statement():
    return [function_in_bracket, line_comment, function, declaration]

def statements():
    return ZeroOrMore(ws, statement), ws

def javascript():
    return statements, EOF


parser = ParserPython(javascript, debug=False, memoization=False, skipws=False)

filename = 'sample.js'
with io.open(filename, encoding='utf-8') as f:
    feed = f.read()
parsed_tree = parser.parse(feed)

# import pdb; pdb.set_trace()
generate_html(parsed_tree, 'output.html')
