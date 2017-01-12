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


class ConditionalSnippet(Snippet):

    def __init__(self, text='', text_begin='', text_end=''):
        super(ConditionalSnippet, self).__init__(text, text_begin, text_end)
        self.conditions = []

    def parse(self, generator):
        print_if_debug(self.text_begin, color=True)

        # if (condition) { ... }
        #   ^ optional
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        # if (condition) { ... }
        #    ^
        if not (tokentype == Token.Punctuation and value == BRACKET_ROUND_OPEN):
            raise_unexpected_exception(value, self.text_begin)
        print_if_debug(BRACKET_ROUND_OPEN, color=True)
        self.text_begin += BRACKET_ROUND_OPEN

        # if (condition) { ... }
        #     ^
        self.parse_condition(generator)

        # if (condition) { ... }
        #              ^
        print_if_debug(BRACKET_ROUND_CLOSE, color=True)
        self.text_begin += BRACKET_ROUND_CLOSE

        # if (condition) { ... }
        #               ^
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        if tokentype == Token.Punctuation and value == BRACKET_CURLY_OPEN:
            # if (condition) { ... }
            #                ^
            print_if_debug(BRACKET_CURLY_OPEN, color=True)
            self.text_begin += BRACKET_CURLY_OPEN

            # if (condition) { ... }
            #                 ^
            super(ConditionalSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_CURLY_CLOSE))

            # if (condition) { ... }
            #                      ^
            print_if_debug(BRACKET_CURLY_CLOSE, color=True)
            self.text = BRACKET_CURLY_CLOSE
        else:
            # if (condition) code;
            #                ^
            until = (Token.Punctuation, SEMICOLON)
            super(ConditionalSnippet, self).parse(generator, until=until, cur_yield=(tokentype, value))
            print_if_debug(SEMICOLON, color=True)
            self.text = SEMICOLON

    def parse_else(self, generator, value):
        print_if_debug(value, color=True)
        self.text += value

        # else { ... }
        # else code;
        #     ^
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text += skipped_value

        if tokentype == Token.Punctuation and value == BRACKET_CURLY_OPEN:
            # else { ... }
            #      ^
            print_if_debug(BRACKET_CURLY_OPEN, color=True)
            self.text += BRACKET_CURLY_OPEN

            # if (condition) { ... }
            #                 ^
            super(ConditionalSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_CURLY_CLOSE))

            # if (condition) { ... }
            #                      ^
            print_if_debug(BRACKET_CURLY_CLOSE, color=True)
            self.text_end = BRACKET_CURLY_CLOSE
        else:
            # else code;
            #      ^
            until = (Token.Punctuation, SEMICOLON)
            super(ConditionalSnippet, self).parse(generator, until=until, cur_yield=(tokentype, value))
            print_if_debug(SEMICOLON, color=True)
            self.text_end += SEMICOLON

    def parse_condition(self, generator):
        super(ConditionalSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_ROUND_CLOSE))
        self.conditions = self.children
        for snippet in self.conditions:
            self.text_begin += snippet.text_begin + snippet.text + snippet.text_end
        self.children = []
