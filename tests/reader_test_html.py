"""Inspect projected HTML structure; this does not emulate MediaWiki or a browser."""
from html.parser import HTMLParser
import re


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def find_all(self, class_name):
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if class_name in child.attrs.get('class', '').split():
                    result.append(child)
                result.extend(child.find_all(class_name))
        return result

    @property
    def text(self):
        if self.attrs.get('aria-hidden') == 'true':
            return ''
        text = ''.join(child.text if isinstance(child, Node) else child for child in self.children)
        return re.sub(r'\[\[File:[^\]]*\]\]', '', text).strip()


class ProjectedHTML(HTMLParser):
    def __init__(self, markup):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        node.start = self.getpos()
        self.stack[-1].children.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack[index].end = self.getpos()
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def nodes(markup, class_name):
    return ProjectedHTML(markup).root.find_all(class_name)


def weapon_unit(markup, anchor):
    unit, = [node for node in nodes(markup, 'td2-weapon-unit') if node.attrs.get('id') == anchor]
    if unit.tag != 'div':
        raise AssertionError('The weapon model wrapper must survive the Wiki HTML filter')
    lines = [0, *(m.end() for m in re.finditer('\n', markup))]
    def offset(position):
        line, column = position
        return lines[line - 1] + column
    return markup[offset(unit.start):offset(unit.end) + len('</div>')]


def equipment_rows(markup):
    rows = []
    for row in nodes(markup, 'td2-equipment-row'):
        labels, values = row.find_all('td2-row-label'), row.find_all('td2-row-value')
        if len(labels) != 1 or len(values) != 1:
            raise AssertionError('Each equipment row must contain one label and one value')
        rows.append((labels[0].text, values[0].text))
    return rows
