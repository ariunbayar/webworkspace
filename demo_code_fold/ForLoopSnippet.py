from pygments.token import Token

from Snippet import Snippet
from utils import print_if_debug
from utils import raise_unexpected_exception
from utils import (
    SEMICOLON,
    BRACKET_ROUND_OPEN,
    BRACKET_ROUND_CLOSE,
    BRACKET_CURLY_OPEN,
    BRACKET_CURLY_CLOSE,
)


class ForLoopSnippet(Snippet):

    def __init__(self, text='', text_begin='', text_end=''):
        super(ForLoopSnippet, self).__init__(text, text_begin, text_end)
        self.conditions = []

    def parse(self, generator):
        print_if_debug(self.text_begin, color=True)
        # for (expressions) { ... }
        #    ^ optional
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        # for (expressions) { ... }
        #     ^ optional
        if not (tokentype == Token.Punctuation and value == BRACKET_ROUND_OPEN):
            raise_unexpected_exception(value, self.text_begin)
        print_if_debug(BRACKET_ROUND_OPEN, color=True)
        self.text_begin += BRACKET_ROUND_OPEN

        # for (expressions) { ... }
        #      ^
        self.parse_expression(generator)

        # for (expressions) { ... }
        #                 ^
        print_if_debug(BRACKET_ROUND_CLOSE, color=True)
        self.text_begin += BRACKET_ROUND_CLOSE

        # for (expressions) { ... }
        #                  ^
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        if tokentype == Token.Punctuation and value == BRACKET_CURLY_OPEN:
            # for (expressions) { ... }
            #                   ^
            print_if_debug(BRACKET_CURLY_OPEN, color=True)
            self.text_begin += BRACKET_CURLY_OPEN

            # if (condition) { ... }
            #                 ^
            super(ForLoopSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_CURLY_CLOSE))

            # if (condition) { ... }
            #                      ^
            print_if_debug(BRACKET_CURLY_CLOSE, color=True)
            self.text_end = BRACKET_CURLY_CLOSE
        else:
            # for (expressions) statement;
            #                   ^
            until = (Token.Punctuation, SEMICOLON)
            super(ForLoopSnippet, self).parse(generator, until=until, cur_yield=(tokentype, value))
            print_if_debug(SEMICOLON, color=True)
            self.text_end = SEMICOLON

    def parse_expression(self, generator):
        super(ForLoopSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_ROUND_CLOSE))
        self.expressions = self.children
        for snippet in self.expressions:
            self.text_begin += snippet.text_begin + snippet.text + snippet.text_end
        self.children = []
