"""Brand identity card contract; does not claim live MediaWiki acceptance."""
from pathlib import Path
import unittest

from wiki_subset import WikiSubset
from reader_test_html import nodes

ROOT = Path(__file__).resolve().parents[1]


class InfoboxImageBackgroundTests(unittest.TestCase):
    def setUp(self):
        from tools.brand_sets.brands import load_catalog
        self.brand = load_catalog(ROOT)['brands'][0]

    def call(self, quality=None, files=(), **names):
        wiki = WikiSubset(ROOT, existing_files=files)
        params = {'图标品牌':self.brand['entity_ref'],'套装全称': self.brand['zh_name'], '英文原名': self.brand['en_name']}
        params.update(names)
        if quality is not None:
            params['品质'] = quality
        output = wiki.template('品牌套装信息框', params)
        self.assertEqual(wiki.infobox_calls, [])
        return output

    def test_card_replaces_native_infobox_and_keeps_frame(self):
        output = self.call()
        self.assertIn('td2-brand-infobox-frame td2-brand-infobox td2-frame', output)
        self.assertEqual(output.count('class="td2-corner-node '), 4)
        self.assertIn('data-icon-key="equipment_slot/backpack"', output)
        self.assertNotIn('state/proficient', output)
        self.assertNotIn('精通', output)

    def test_quality_labels_follow_existing_quality_parameter(self):
        self.assertIn('<span>顶级</span>', self.call())
        for quality, expected, label in [('high_end', 'high_end', '顶级'),
                                         ('gear_set', 'gear_set', '装备组'),
                                         ('exotic', 'exotic', '奇特'),
                                         ('unknown', 'neutral', ''), ('', 'neutral', '')]:
            with self.subTest(quality=quality):
                output = self.call(quality)
                self.assertIn('td2-quality-' + expected, output)
                self.assertIn('<span>' + label + '</span>', output)

    def test_existing_logo_resolver_and_missing_file(self):
        filename = self.brand['wiki_filename']
        for files in ((), ['File:' + filename]):
            output = self.call(files=files)
            logos = nodes(output, 'td2-brand-logo')
            self.assertEqual(len(logos), 1)
            self.assertEqual(len(logos[0].find_all('td2-logo-art')), 1)
            self.assertEqual(output.count('[[File:' + filename + '|'), 1)
            self.assertIn('[[File:' + filename + '|link=|alt=' + self.brand['zh_name'] + ']]', output)
        missing = self.call(**{'套装全称':'NON-GAME-FACT unmapped brand', '图标品牌':'unknown-id'})
        self.assertEqual(nodes(missing, 'td2-brand-logo')[0].text, '')
        self.assertNotIn('[[File:' + filename + '|', missing)
        self.assertIn('data-icon-key="equipment_slot/backpack"', missing)

    def test_card_names_are_independent_even_when_equal(self):
        for zh, en in [('测试中文品牌', 'Test Brand'), ('', 'Test Brand'),
                       ('测试中文品牌', ''), ('', ''), ('5.11 Tactical', '5.11 Tactical')]:
            with self.subTest(zh=zh, en=en):
                output = self.call(**{'套装全称': zh, '英文原名': en})
                self.assertEqual([n.text for n in nodes(output, 'td2-brand-name-zh')], [zh] if zh else [])
                self.assertEqual(nodes(output, 'td2-brand-name-en'), [])
                page = WikiSubset(ROOT).template('品牌套装内容', {'套装全称':zh, '英文原名':en})
                self.assertEqual([n.text for n in nodes(page, 'td2-brand-name-zh')], [zh] if zh else [])
                self.assertEqual([n.text for n in nodes(page, 'td2-brand-name-en')], [en] if en else [])
                self.assertIn('<span>顶级</span>', output)


if __name__ == '__main__':
    unittest.main()
