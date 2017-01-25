"""
Test whether generate_image.py generates according to GVim syntax
"""

import io
import re
import sys
import subprocess

from bs4 import BeautifulSoup
from bs4.element import NavigableString

from parse import parse_file, generate_image


def cmd(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT)


def iter_soup_chars(soup, styles):
    yield(-1, -1, styles['body']['background-color'])

    x = 1
    y = 1
    for i, el in enumerate(soup.contents):
        is_span = el.name == 'span'
        is_string = isinstance(el, NavigableString)
        is_newline = is_string and str(el).endswith('\n')

        if i == 0 and is_newline:
            continue

        if is_span:
            if el['class'][0] == 'LineNr':
                continue
            color = styles[el['class'][0]]['color']
            text = el.string
        elif is_string:
            color = styles['body']['color']
            text = str(el)
        else:
            raise ValueError('unknown type: ' + type(el))

        for char in text:
            if char == '\n':
                x = 0
                y += 1
            elif char == ' ':
                pass
            else:
                yield(y, x, color)
            x += 1


def read_vim_gen_html(filename):
    with io.open(filename, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    styles = {}
    for content in soup.html.head.style.contents:
        content = content
        re_styles = re.compile('^([^{]+){([^}]+)}$', re.M)
        matches = re_styles.findall(content)
        for sel, str_props in matches:
            sel = sel.strip()
            props = map(lambda v: v.split(':'), str_props.split(';'))
            props = filter(lambda v: len(v) > 1, props)
            props = map(lambda v: (v[0].strip(), v[1].strip()), props)
            props = dict(props)
            if 'color' in props:
                props['color'] = props['color']
            if 'background-color' in props:
                props['background-color'] = props['background-color']
            if sel == 'body':
                styles[sel] = props
            elif sel.startswith('.'):
                styles[sel[1:]] = props

    return (soup.html.body.pre, styles)


def run_test(filename, html_file):
    lexer_result, rows, columns = parse_file(filename)
    iter_parser = generate_image(lexer_result, rows, columns, "output.png", is_test=True)

    soup, styles = read_vim_gen_html(html_file)
    iter_soup = iter_soup_chars(soup, styles)

    for row, column, color in iter_parser:
        row1, column1, color1 = next(iter_soup)
        if (row, column, color) != (row1, column1, color1):
            print((row, column, color))
            print((row1, column1, color1))
            raise Exception('unexpected %s at %s, %s' % (color, row, column))

    return True


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print()
        print('usage: python parse_test.py <script_to_test_syntax>')
        print()

    else:
        filename = sys.argv[1]
        html_file = "/run/shm/tohtml.html"


        cmd("gvim", "-f", "-c", "TOhtml", "-c", "w! %s | qa!" % html_file, filename)

        if run_test(filename, html_file):
            print('--- TEST was successful! ---')
