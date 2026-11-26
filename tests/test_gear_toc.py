from tools import identity as identity_catalog
import json
import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class Outline(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.headings = []
        self.ids = []
        self.current = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.append(values['id'])
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.current = [tag, '']

    def handle_data(self, data):
        if self.current is not None:
            self.current[1] += data

    def handle_endtag(self, tag):
        if self.current is not None and tag == self.current[0]:
            text = re.sub(r'\[\[File:[^\]]+\]\]', '', self.current[1])
            text = re.sub(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]', r'\1', text)
            self.headings.append((tag, text.strip()))
            self.current = None


class GearTocTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = identity_catalog.read_json(ROOT / 'data/gear-sets/sets.json')['sets']
        cls.view = WikiSubset(ROOT)


    def test_all_gear_pages_emit_references_after_expertise_inside_footer(self):
        for entity in self.catalog:
            with self.subTest(title=entity['title']):
                raw = (ROOT / entity['source']).read_text(encoding='utf8')
                text = self.view.expand(raw, {})
                footer = text[text.index('<div class="td2-brand td2-gear-footer">'):]
                self.assertEqual(text.count('<references/>'), 1)
                self.assertLess(footer.index('td2-expertise-card'), footer.index('<references/>'))
                self.assertRegex(footer, r'<references/></div>\s*<div class="td2-navbox"')
                self.assertLess(text.rfind('<h2'), text.index('<references/>'))

    def test_heading_card_default_is_unchanged_and_gear_opt_out_is_structural(self):
        args = {'中文名称': '面具', '英文名称': 'mask', '图标键': 'mask'}
        original = self.view.template('装备标题卡', args)
        plain = self.view.template('装备标题卡', {**args, '章节标题': '否'})
        self.assertEqual(Outline(original).headings, [('h3', '面具mask')])
        self.assertEqual(Outline(plain).headings, [])
        self.assertNotIn('role="heading"', plain)
        restored = plain.replace('<div class="td2-equipment-heading-card', '<h3 class="td2-equipment-heading-card', 1)
        self.assertEqual(re.sub(r'</div>(\s*)$', r'</h3>\1', restored), original)
