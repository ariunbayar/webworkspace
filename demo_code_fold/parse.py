import sys
import io
from pygments import lex
from pygments.lexers.javascript import JavascriptLexer

from Snippet import Snippet


filename = sys.argv[1]
with io.open(filename, encoding='utf-8') as f:
    feed = f.read()


tokentype_values = lex(feed, JavascriptLexer())
root_snippet = Snippet()
root_snippet.parse(tokentype_values)


def print_snippet(snippets, level=0):
    print('-%s->' % level, end='')
    for snippet in snippets:
        nested_classes = [
            BracketRoundSnippet,
            FunctionSnippet,
            ConditionalSnippet
        ]

        if any([isinstance(snippet, c) for c in nested_classes]):
            print(snippet.text_begin, end='')
            print_snippet(snippet.children, level + 1)
            print(snippet.text_end, end='')
        else:
            print(snippet.text, end='')

    print('<-%s-' % level, end='')

print_snippet(root_snippet.children)
