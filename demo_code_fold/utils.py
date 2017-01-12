NEWLINE = '\n'
SPACE = ' '
COMMA = ','
QUOTE = '\''
QUOTE_DBL = '\"'
BACKSLASH = '\\'
SEMICOLON = ';'

BRACKET_CURLY_OPEN = '{'
BRACKET_CURLY_CLOSE = '}'
BRACKET_ROUND_OPEN = '('
BRACKET_ROUND_CLOSE = ')'

# TODO the value looks weird
COMMENT_SINGLE_LINE = 'single line comment'
COMMENT_MULTI_LINE = 'multi line comment'

DEBUG = True

n = 100


def print_if_debug(value, color=False):
    global n
    # n -= 1
    if n == 0:
        raise Exception('debug stop')
    if DEBUG:
        # print("\033[42m%s\033[49m" % value, end='')
        if color:
            print("\033[92m\033[42m%s\033[0m\033[49m" % value, end='')
        else:
            print(value, end='')


def raise_unexpected_exception(value, text):
    raise Exception("Unexpected '%s' after '%s'" % (value, text))
