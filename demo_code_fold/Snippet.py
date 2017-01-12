from pygments.token import Token

from utils import print_if_debug
from utils import (
    NEWLINE,
    SPACE,
    BRACKET_ROUND_OPEN,
    BRACKET_ROUND_CLOSE,
    BRACKET_CURLY_CLOSE
)


class Snippet(object):
    def __init__(self, text='', text_begin='', text_end=''):
        self.text = text
        self.parent = None
        self.children = []
        self.text_begin = text_begin
        self.text_end = text_end

    def append(self, snippet):
        snippet.parent = self
        self.children.append(snippet)

    def _parse(self, generator, tokentype, value):
        if tokentype == Token.Text and value == '':
            # no idea why lexer does it
            return

        if tokentype == Token.Comment.Single:
            print_if_debug(value)
            self.append(CommentSnippet(value))
            return

        if tokentype == Token.Keyword.Declaration and value == 'function':
            snippet = FunctionSnippet(text_begin=value)
            self.append(snippet)
            try:
                snippet.parse(generator)
            except StopIteration:
                # TODO it doesn't feel right, what if for loop swallows it
                raise Exception('end of file reached')
            return

        if tokentype == Token.Keyword and value == 'if':
            snippet = ConditionalSnippet(text_begin='if')
            self.append(snippet)
            try:
                snippet.parse(generator)

                tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
                print_if_debug(skipped_value)

                if tokentype == Token.Keyword and value == 'else':
                    snippet.parse_else(generator, value)
                else:
                    return self._parse(generator, tokentype, value)

            except StopIteration:
                # TODO it doesn't feel right, what if for loop swallows it
                raise Exception('end of file reached')
            return

        if tokentype == Token.Keyword and value == 'for':
            snippet = ForLoopSnippet(text_begin='for')
            self.append(snippet)
            snippet.parse(generator)
            return

        if False and tokentype == Token.Punctuation and value == BRACKET_CURLY_CLOSE:
            # print_if_debug(BRACKET_CURLY_CLOSE)
            # TODO must be enabled after all cases been implemented
            # raise Exception("closing bracket '}' found when no opening was present")
            pass

        if tokentype == Token.Punctuation and value == BRACKET_ROUND_OPEN:
            print_if_debug(BRACKET_ROUND_OPEN)
            snippet = BracketRoundSnippet(text_begin=value)
            self.append(snippet)
            tokentype, value = snippet.parse(generator, until=(Token.Punctuation, BRACKET_ROUND_CLOSE))
            print_if_debug(BRACKET_ROUND_CLOSE)
            snippet.text_end = BRACKET_ROUND_CLOSE
            return

        print_if_debug(value)
        self.append(Snippet(value))  # TODO throw exception. Undeclared token found

    def parse(self, generator, until=None, cur_yield=None):
        if cur_yield:
            tokentype, value = cur_yield
            if until and until == (tokentype, value):
                return tokentype, value
            self._parse(generator, tokentype, value)

        for tokentype, value in generator:
            if until and until == (tokentype, value):
                return tokentype, value
            self._parse(generator, tokentype, value)

        if until:
            import pdb; pdb.set_trace()
            raise Exception("Expected '%s'" % until[1])

    def next_if_spaces_or_raise(self, generator, optional=True):
        tokentype, value = next(generator)
        skipped_value = ''
        if tokentype == Token.Text:

            if (optional or len(value) > 0) and (value.count(SPACE) + value.count(NEWLINE)) == len(value):
                skipped_value = value
                tokentype, value = next(generator)
            else:
                raise Exception("unexpected '%s'" % value)
        return tokentype, value, skipped_value


from CommentSnippet import CommentSnippet
from ConditionalSnippet import ConditionalSnippet
from FunctionSnippet import FunctionSnippet
from BracketRoundSnippet import BracketRoundSnippet
from ForLoopSnippet import ForLoopSnippet
