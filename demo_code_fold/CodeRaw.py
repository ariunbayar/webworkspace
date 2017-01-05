from __future__ import print_function
from utils import (
    SPACE,
    NEWLINE,
    QUOTE,
    QUOTE_DBL,
    BACKSLASH
    )


echo = lambda v: print(v.encode('utf-8'), end='')


class Snippet:
    def __init__(self, text):
        self.begin_text = ''
        self.text = text
        self.end_text = ''

    def __str__(self):
        return self.begin_text + self.text + self.end_text


class StringSnippet(Snippet):
    def __init__(self, begin_text, text, end_text):
        self.begin_text = begin_text
        self.text = text
        self.end_text = end_text


class CommentSnippet(Snippet):

    def __init__(self, begin_text, text, end_text):
        self.begin_text = begin_text
        self.text = text
        self.end_text = end_text
        self.is_multiline = len(text.splitlines()) > 1


class CodeRaw:

    def __init__(self, data):
        self.data = data
        self.row_length = [len(line) for line in self.data]
        self.last_line = len(self.data) - 1
        # these values should be incremented by 1 for presentation
        self.row = 0
        self.col = 0

        # javascript rules
        self.rules = {
            'line-comment': {
                'begin': '//',
                'end': '\n',
            },
            'block-comment': {
                'begin': '/*',
                'end': '*/',
            },
            'string-double-quote': {
                'begin': QUOTE_DBL,
                'end_invalid': BACKSLASH + QUOTE_DBL,
                'end': QUOTE_DBL,
            },
            'string-single-quote': {
                'begin': QUOTE,
                'end_invalid': BACKSLASH + QUOTE,
                'end': QUOTE,
            },
        }

        self.rule_begin_indices = self.generate_rule_indices(self.rules)

        self.snippets = []

    def generate_rule_indices(self, rules):
        rule_indices = {}

        for rule_name, rule in rules.iteritems():
            begin_text_len = len(rule['begin'])
            branch = rule_indices
            for i in range(begin_text_len):
                ch = rule['begin'][i]
                if i < begin_text_len - 1:
                    if ch not in branch:
                        branch[ch] = {}
                    branch = branch[ch]
                else:
                    branch[ch] = rule_name

        return rule_indices

    def is_eof(self):
        if self.row == self.last_line + 1:
            return True
        else:
            return False

    def is_eol(self):
        # TODO usage
        return self.col == self.row_length[self.row] - 1

    def seek_get_char(self):
        if self.is_eof():
            return ''

        ch = self.data[self.row][self.col]
        if self.is_eol():
            self.row += 1
            self.col = 0
        else:
            self.col += 1

        return ch

    def seek_get_indent(self):
        if self.is_eof():
            raise Exception('cant get indent when finished reading content')

        if self.col != 0:
            raise Exception('cant get indent when not finished seeking row %s.' % (self.row + 1))

        first_char = self.data[self.row][self.col]

        if first_char == NEWLINE:
            return ''

        if first_char != SPACE:
            return ''

        # find how many spaces the line starts with
        num_spaces = 0
        for i in range(self.row_length[self.row]):
            ch = self.data[self.row][i]
            if ch == NEWLINE or ch != SPACE:
                self.col = i
                break
            num_spaces += 1

        return ' ' * num_spaces

    def seek_eol(self):
        if self.is_eof():
            raise Exception('cant get seek when finished reading content')
        text = self.data[self.row][self.col:-1]
        self.row += 1
        self.col = 0

        return text

    def seek_rule_begin(self):
        rule_name = None
        snippet = ''
        rule_index = self.rule_begin_indices
        while not self.is_eof():
            ch = self.seek_get_char()
            snippet += ch

            if ch in rule_index:
                rule_index = rule_index[ch]
            else:
                rule_index = self.rule_begin_indices

            if type(rule_index) == str:
                rule_name = rule_index
                # remove rule beginning from prepending snippet
                begin_len = len(self.rules[rule_name]['begin'])
                snippet = snippet[:-begin_len]

                break

        return rule_name, snippet

    def seek_rule_end(self, rule_name):
        snippet = ''

        rule = self.rules[rule_name]
        rule_end_len = len(rule['end'])
        i = 0
        while not self.is_eof():
            ch = self.seek_get_char()
            snippet += ch

            if ch == rule['end'][i]:
                i += i == rule_end_len and 0 or 1
            else:
                i = 0

            if i == rule_end_len:
                if 'end_invalid' in rule:
                    end_invalid = rule['end_invalid']
                    if snippet[-len(end_invalid):] == end_invalid:
                        i = 0
                        continue
                # remove rule ending from found snippet
                snippet = snippet[:-rule_end_len]
                return snippet

        raise Exception('reached to EOF when ending was not found')

    def parse(self):
        while not self.is_eof():
            # TODO indent is useless for Javascript
            # indent = self.seek_get_indent()

            rule_name, text = self.seek_rule_begin()
            if len(text):
                self.snippets.append(Snippet(text))

            if rule_name is not None:
                text = self.seek_rule_end(rule_name)
                rule = self.rules[rule_name]
                if rule_name in ['string-single-quote', 'string-double-quote']:
                    snippet = StringSnippet(rule['begin'], text, rule['end'])
                if rule_name in ['line-comment', 'block-comment']:
                    snippet = CommentSnippet(rule['begin'], text, rule['end'])

                self.snippets.append(snippet)

    def dump(self):
        for snippet in self.snippets:
            if isinstance(snippet, CommentSnippet):
                # echo('\n>> Comment <<\n')
                echo("\033[44m%s\033[49m" % snippet.begin_text)
                echo("\033[95m\033[44m%s\033[0m\033[49m" % snippet.text)
                echo("\033[44m%s\033[49m" % snippet.end_text)
            elif isinstance(snippet, StringSnippet):
                # echo('\n>> String <<\n')
                echo("\033[42m%s\033[49m" % snippet.begin_text)
                echo("\033[92m\033[42m%s\033[0m\033[49m" % snippet.text)
                echo("\033[42m%s\033[49m" % snippet.end_text)
            else:
                # echo('\n>> unknown <<\n')
                echo(snippet.text)
