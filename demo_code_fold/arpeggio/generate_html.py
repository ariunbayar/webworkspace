import io
import os

from jinja2 import Environment, FileSystemLoader


loader = FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates'))
env = Environment(loader=loader)

# TODO line number
# TODO keyword highlighting with color


def declaration_html(tree):
    html = ''

    for node in tree:
        if node.rule_name == '' and node.value == 'var':
            html += "<span class=\"Type\">var</span>"
        elif node.rule_name == 'assignment':
            # naming, Optional(ws, '=', ws, assignables)
            for t in node:
                if t.rule_name == 'naming':
                    html += t.value
                elif t.rule_name == 'ws':
                    html += t.value
                elif t.value == '=':
                    html += "<span class=\"Statement\">=</span>"
                elif t.rule_name == 'assignables':
                    html += assignables_html(t[0])
                else:
                    assert False
        else:
            html += node.value

    return html


def function_in_bracket_html(tree):
    # TODO private = True
    html = ''
    for node in tree:
        if node.rule_name == 'function':
            html += function_html(node)
        elif node.rule_name == 'access':
            html += access_html(node)
        else:
            html += node.value

    return html


def assignables_html(node):
    if node.rule_name == 'function':
        return function_html(node)
    elif node.rule_name == 'object_access':
        return object_access_html(node)
    else:
        template = env.get_template('assignables.html')
        return template.render(node=node)


def obj_html(tree):
    html = ''
    for node in tree:
        if node.rule_name == 'assignables':
            html += assignables_html(node[0])
        else:
            html += node.value
    return html


def access_html(tree):
    html = ''
    for node in tree:
        if node.rule_name == 'obj':
            html += obj_html(node)
        else:
            html += node.value

    return html


def object_access_html(tree):
    html = ''
    for node in tree:
        if node.rule_name == 'obj':
            html += obj_html(node)
        else:
            html += node.value
    return html


def function_html(tree):
    content = ''
    for node in tree:
        if node.rule_name == 'statements':
            content = statements_html(node)
    template = env.get_template('function.html')
    return template.render(tree=tree, content=content)


def comment_html(tree):
    template = env.get_template('comment.html')
    return template.render(tree=tree)


def statements_html(tree):
    html = ''
    for node in tree:
        if node.rule_name == 'statement':
            rn = node[0].rule_name
            if rn == 'function_in_bracket':
                html += function_in_bracket_html(node[0])

            elif rn == 'function':
                html += function_html(node[0])

            elif rn == 'declaration':
                html += declaration_html(node[0])

            elif rn == 'line_comment':
                html += comment_html(node[0])

            else:
                assert False

        elif node.rule_name == 'ws':
            html += node.value

        else:
            assert False
            # html += node.rule_name + '???->' + str(node) + '\n'

    return html


def generate_html(parsed_tree, filename):
    if parsed_tree.rule_name != 'javascript' or parsed_tree[0].rule_name != 'statements':
        raise Exception("HTML generation expects 'javascript[statements]'")
    else:
        template = env.get_template('layout.html')
        html = template.render(content=statements_html(parsed_tree[0]))

        with io.open(filename, 'w', encoding='utf-8') as f:
            f.write(html)

        return True
