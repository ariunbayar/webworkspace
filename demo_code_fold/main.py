import io
import sys
from rule_javascript import parse


filename = sys.argv[1]
with io.open(filename, encoding="utf-8") as f:
    code = f.readlines()

# TODO test filename extension (js, py, css, html etc)


def update_code_range(code_range, num_line, line, is_new = False):
    if is_new:
        code_range['begin_line'] = num_line
        code_range['begin_column'] = 1  # TODO
    else:
        code_range['end_line'] = num_line
        code_range['end_column'] = len(line)

    return code_range


code_blocks = []


snippet = ''
num_line = 0
code_range = {
    'begin_line'  : 1,
    'begin_column': 1,
    'end_line'    : 1,
    'end_column'  : 1,
}
for line in code:
    num_line += 1
    snippet = snippet + line
    print 'scanning %s' % repr(snippet)
    print '---'

    code_range = update_code_range(code_range, num_line, line, is_new = True)
    parsed_snippet = parse(snippet)
    if parsed_snippet == None:
        continue

    code_range = update_code_range(code_range, num_line, line, is_new = False)
    code_block = {
        'range': code_range.copy(),
        'snippet': parse(snippet),
    }
    code_blocks.append(code_block)
    snippet = ''

print '###'
import pprint
pprint.pprint(code_blocks)
