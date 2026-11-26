import unittest
from pathlib import Path

from current_identity import source_for
from reader_test_html import nodes
from tools import identity
from tools.equipment.wikitext import WikiSubset

ROOT = Path(__file__).resolve().parents[1]
LINK = '<span class="td2-attribute-link">[[威胁度|提升威胁度]]</span>'
REDUCED_LINK = '<span class="td2-attribute-link">[[威胁度|降低威胁度]]</span>'


class AttributeLinksTests(unittest.TestCase):
    def setUp(self):
        self.reader = WikiSubset(ROOT)

    def test_target_is_registered_mechanic_not_equipment(self):
        entry = next(row for row in identity.registry(ROOT) if row['id'] == 'mechanic-threat')
        self.assertEqual((entry['namespace'], entry['title']), (0, '威胁度'))
        self.assertEqual(entry['source'], 'wiki/pages/mechanics/威胁度.wiki')

    def test_brands_share_link_and_keep_mode_values(self):
        for name, value in [('5.11 Tactical', '100'), ('贝尔斯通军火', '100'), ('戈兰装备有限公司', '150')]:
            with self.subTest(name=name):
                rendered = self.reader.expand(source_for(name).read_text('utf8'), {})
                self.assertEqual(rendered.count(LINK), 2)
                self.assertEqual(rendered.count('<strong>+' + value + '%</strong> ' + LINK), 2)

    def test_named_equipment_uses_same_mapping_without_changing_number(self):
        rendered = self.reader.expand(source_for('灾祸装备').read_text('utf8'), {})
        self.assertIn('50.0% [[威胁度|降低威胁度]]', [row.text for row in nodes(rendered, 'td2-row-value')])
        self.assertIn(REDUCED_LINK, self.reader.template('TD2次属性名称', {'1': 'minor_attribute_reduced_threat'}))
        self.assertIn(LINK, self.reader.template('TD2词条名称', {'1': 'bonus_increased_threat'}))

    def test_requires_exact_attribute_identity_and_name(self):
        for attr, name in [('unrelated', '威胁度'), ('', '威胁度'), ('bonus_increased_threat', '威胁度变动'),
                           ('bonus_increased_threat', '[[威胁度]]'), ('minor_attribute_reduced_threat', '提升威胁度')]:
            with self.subTest(attr=attr, name=name):
                self.assertEqual(self.reader.expand('{{#invoke:TD2资料记录|attributeName|id=' + attr + '|name=' + name + '}}', {}), name)

    def test_free_text_and_talent_names_are_not_linked(self):
        raw = '普通正文中的威胁度。{{#invoke:TD2资料记录|render|records={{装备效果|效果ID=test|模式=PvE|属性ID=bonus_increased_threat|属性=提升威胁度|数值=100|单位=%|描述=普通描述中的威胁度。}}}}'
        rendered = self.reader.expand(raw, {})
        self.assertEqual(rendered.count(LINK), 1)
        self.assertIn('普通正文中的威胁度。', rendered)
        self.assertIn('普通描述中的威胁度。', rendered)
        talent = '{{#invoke:TD2资料记录|render|records={{装备效果|效果ID=test|模式=PvE|名称=威胁度|描述=威胁度}}}}'
        self.assertNotIn('td2-attribute-link', self.reader.expand(talent, {}))


if __name__ == '__main__':
    unittest.main()
