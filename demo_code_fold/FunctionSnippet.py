from pygments.token import Token

from Snippet import Snippet
from utils import print_if_debug
from utils import raise_unexpected_exception
from utils import (
    COMMA,
    BRACKET_ROUND_OPEN,
    BRACKET_ROUND_CLOSE,
    BRACKET_CURLY_OPEN,
    BRACKET_CURLY_CLOSE
)

class FunctionSnippet(Snippet):

    def __init__(self, text='', text_begin='', text_end=''):
        super(FunctionSnippet, self).__init__(text, text_begin, text_end)
        self.arguments = []
        self.name = []

    def parse(self, generator):
        print_if_debug(self.text_begin, color=True)

        # function func1 ( arg1 , arg2 ) { ... }
        #         ^ optional for 'function(){ ... }'
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        # function func1 ( arg1 , arg2 ) { ... }
        #          ^ optional
        if tokentype == Token.Name.Other:
            print_if_debug(value, color=True)
            self.name = value
            self.text_begin += value

            # function func1 ( arg1 , arg2 ) { ... }
            #               ^ optional
            tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
            print_if_debug(skipped_value, color=True)
            self.text_begin += skipped_value

        # function func1 ( arg1 , arg2 ) { ... }
        #                ^
        if not (tokentype == Token.Punctuation and value == BRACKET_ROUND_OPEN):
            raise_unexpected_exception(value, self.text_begin)
        print_if_debug(BRACKET_ROUND_OPEN, color=True)
        self.text_begin += BRACKET_ROUND_OPEN

        # function func1 ( arg1 , arg2 ) { ... }
        #                 ^ optional
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        # function func1 ( arg1 , arg2 ) { ... }
        #                  ^
        while tokentype == Token.Name.Other:
            self.arguments.append(value)
            print_if_debug(value, color=True)
            self.text_begin += value

            # function func1 ( arg1 , arg2 ) { ... }
            #                      ^ optional
            tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
            print_if_debug(skipped_value, color=True)
            self.text_begin += skipped_value

            # function func1 ( arg1 , arg2 ) { ... }
            #                       ^ optional
            if tokentype == Token.Punctuation and value == COMMA:
                print_if_debug(COMMA, color=True)
                self.text_begin += COMMA

                # function func1 ( arg1 , arg2 ) { ... }
                #                        ^ optional
                tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
                print_if_debug(skipped_value, color=True)
                self.text_begin += skipped_value

        # function func1 ( arg1 , arg2 ) { ... }
        #                              ^
        if not (tokentype == Token.Punctuation and value == BRACKET_ROUND_CLOSE):
            raise_unexpected_exception(value, self.text_begin)
        print_if_debug(BRACKET_ROUND_CLOSE, color=True)
        self.text_begin += BRACKET_ROUND_CLOSE

        # function func1 ( arg1 , arg2 ) { ... }
        #                               ^ optional
        tokentype, value, skipped_value = self.next_if_spaces_or_raise(generator)
        print_if_debug(skipped_value, color=True)
        self.text_begin += skipped_value

        # function func1 ( arg1 , arg2 ) { ... }
        #                                ^
        if not (tokentype == Token.Punctuation and value == BRACKET_CURLY_OPEN):
            raise_unexpected_exception(value, self.text_begin)
        print_if_debug(BRACKET_CURLY_OPEN, color=True)
        self.text_begin += BRACKET_CURLY_OPEN

        super(FunctionSnippet, self).parse(generator, until=(Token.Punctuation, BRACKET_CURLY_CLOSE))

        print_if_debug(BRACKET_CURLY_CLOSE, color=True)
        self.text_end = BRACKET_CURLY_CLOSE
