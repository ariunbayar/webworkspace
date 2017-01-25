import re

from PIL import ImageFont
from PIL import Image
from PIL import ImageDraw

from bs4 import BeautifulSoup
from bs4.element import NavigableString


# XXX this file is completely replaced with following
# pygmentize -f png -O font_name='DejaVuSansMono',style=solarizeddark,font_size=54,line_number_chars=3 -o test.png web/assets/Browser.js; display test.png
# see: http://pygments.org/docs/quickstart/#example


class Canvas:

    def __init__(self, color_bg, columns, rows, fontsize, line_spacing):
        self.resolution_fix = 4

        self.fontsize = fontsize * self.resolution_fix
        self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", self.fontsize)

        self.line_spacing = int(line_spacing * self.resolution_fix)
        self.line_width, self.line_height = self.font.getsize('A')

        self.size = (int(columns * self.line_width), int(rows * (self.line_height + self.line_spacing)))
        self.img = Image.new("RGBA", self.size, color_bg)

    def write(self, text, column, row, color):
        draw = ImageDraw.Draw(self.img)
        x = (column - 1) * self.line_width
        y = (row - 1) * (self.line_height + self.line_spacing)
        draw.text((x, y), text, color, self.font, spacing=self.line_spacing)

    def _scale_down(self, size, scale):
        return (int(size[0] * scale), int(size[1] * scale))

    def _save(self, filename, scale):
        size = self._scale_down(self.size, float(scale) / self.resolution_fix)
        img = self.img.resize(size, Image.ANTIALIAS)
        img.save(filename)

    def save(self):
        self._save('create_image_regular.png', 1)
        self._save('create_image_small.png', 0.25)


def draw_soup(soup, styles, columns, rows, fontsize, line_spacing):

    color_bg = styles['body']['background-color']
    canvas = Canvas(color_bg, columns, rows, fontsize, line_spacing)

    x = 1
    y = 1
    for i, el in enumerate(soup.contents):
        is_span = el.name == 'span'
        is_string = isinstance(el, NavigableString)
        is_newline = is_string and unicode(el).endswith('\n')

        if i == 0 and is_newline:
            continue

        if is_span:
            # TODO bold, italic
            color = styles[el['class'][0]]['color']
            text = el.string
        elif is_string:
            color = styles['body']['color']
            text = unicode(el)
        else:
            raise ValueError('unknown type: ' + type(el))

        canvas.write(text, x, y, color)

        if is_newline:
            x = 1
            y += 1
        else:
            x += len(text)

    canvas.save()


def color_hex2rgb(color):
    return (
        int(color[1:3], 16),
        int(color[3:5], 16),
        int(color[5:7], 16),
    )


def read_vim_gen_html(filename):
    with open(filename) as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    styles = {}
    for content in soup.html.head.style.contents:
        content = unicode(content)
        re_styles = re.compile('^([^{]+){([^}]+)}$', re.M)
        matches = re_styles.findall(content)
        for sel, str_props in matches:
            sel = sel.strip()
            props = map(lambda v: v.split(':'), str_props.split(';'))
            props = filter(lambda v: len(v) > 1, props)
            props = map(lambda v: (v[0].strip(), v[1].strip()), props)
            props = dict(props)
            if 'color' in props:
                props['color'] = color_hex2rgb(props['color'])
            if 'background-color' in props:
                props['background-color'] = color_hex2rgb(props['background-color'])
            if sel == 'body':
                styles[sel] = props
            elif sel.startswith('.'):
                styles[sel[1:]] = props

    return (soup.html.body.pre, styles)


def get_size_in_chars(filename):
    columns = 0
    rows = 0
    with open(filename) as f:
        for line in f:
            rows += 1
            columns = max(len(line), columns)

    return (columns, rows)


filename = 'web/assets/Browser.js'
columns, rows = get_size_in_chars(filename)

soup, styles = read_vim_gen_html('/run/shm/tohtml.html')

# fontsize = 18
fontsize = 4
spacing = fontsize / 4.5

draw_soup(soup, styles, columns, rows, fontsize, spacing)
