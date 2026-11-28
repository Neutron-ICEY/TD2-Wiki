from current_identity import entity_id, source_for, material_id, asset_file
from tools import identity as identity_catalog
import copy
import json
from pathlib import Path
import re
import unittest

from tools.brand_sets.equipment import dismantle_materials, load_equipment, validate_ui
from tools.brand_sets.knowledge import description_html, validate_talents
from wiki_subset import WikiSubset
from fixture_corpus import corpus_path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = corpus_path('dist/brand-data-completeness-20261021-001')


class BrandDataCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.base, self.ui = load_equipment(ROOT)
        self.talents = identity_catalog.read_json(ROOT / 'data/brand-sets/talents.json')
        self.files = {'File:' + p.name for p in (ROOT / 'assets').iterdir() if p.is_file()}
        self.wiki = WikiSubset(ROOT, self.files)

    def test_complete_names_are_literal_and_blank_does_not_invent_material(self):
        name = '中国光能工业公司 FZP 织物'
        for slot in self.base['部位']:
            rendered = self.wiki.template('TD2分解规则', {'1': slot, '品牌材料': name, '品牌': entity_id('中国光能工业公司')})
            self.assertIn('[[' + name + '|' + name + ']]', rendered)
            self.assertIn('TD2-Brand-ChinaLightIndustriesCorporation-Logo.png', rendered)
            self.assertEqual(rendered.count('td2-material-row '), 5)
            self.assertNotIn('品牌材料名称待填写', rendered)
            blank = self.wiki.template('TD2分解规则', {'1': slot, '品牌': entity_id('中国光能工业公司')})
            self.assertEqual(blank.count('td2-material-row '), 4)
            self.assertNotIn('中国光能工业公司材料', blank)
            self.assertNotIn('品牌材料名称待填写', blank)
            self.assertEqual(dismantle_materials(self.base, '', slot, self.ui), [row for row in dismantle_materials(self.base, name, slot, self.ui) if row[0] != name])
        self.assertEqual(self.wiki.template('TD2材料行', {'名称': '', '品牌': entity_id('中国光能工业公司'), '数量': '1'}).strip(), '')

    def test_material_identity_is_independent_of_display_name(self):
        validate_ui(self.ui)
        expected = {
            '5.11 Tactical 材料': ('5.11 Tactical', '4CDCE5B25C80F9600002E3817D73B469'),
            '战队合金材料': ('战队合金', 'E03CE5EA68D3DE090003879C81D0404F'),
            '中国光能工业公司 FZP 织物': ('中国光能工业公司', '4CDCE5B25B4762E8000193A435A709D0')}
        for name, (brand, uid) in expected.items():
            row = self.ui['material_display'][material_id(name)]
            self.assertEqual((row['brand_ref'], row['native']['currency_uid']), (entity_id(brand), uid))
            self.assertEqual(row['icon_key'], 'brand_material')
        invalid = copy.deepcopy(self.ui)
        invalid['material_display']['currency:e03ce5ea68d3de090003879c81d0404f']['native']['currency_uid'] = '战队合金'
        with self.assertRaises(ValueError):
            validate_ui(invalid)

    def test_native_dismantle_combines_config_with_observed_fabric_outputs(self):
        old = (REVIEW / 'before/wiki/templates/TD2分解规则.wiki').read_text('utf-8')
        previous = WikiSubset(ROOT, self.files, sources={'wiki/templates/TD2分解规则.wiki': old})
        pattern = r'<span class="td2-material-name">(.*?)</span><span class="td2-material-value"><span class="td2-material-quantity">(.*?)</span>'
        for slot in self.base['部位']:
            args = {'1': slot, '品牌材料': '中国光能工业公司 FZP 织物', '品牌': entity_id('中国光能工业公司')}
            current = self.wiki.template('TD2分解规则', args)
            historic = previous.template('TD2分解规则', args)
            self.assertIn('21–24', historic)
            self.assertNotIn('21–24', current)
            self.assertNotIn('23–46', current)
            self.assertNotIn('0–1', current)
            self.assertEqual(len(re.findall(pattern, current)), 5)
            self.assertIn('<li title="额外产出概率25%。">', current)
            self.assertNotIn('（固定）', current)
            self.assertNotIn('<small>', current)
            self.assertEqual([quantity for _, quantity in re.findall(pattern, current)], ['23 / 46', '0 / 8', '0 / 8', '1', '1'])
            self.assertEqual(re.findall(r'<span class="td2-material-probability">(.*?)</span>', current), ['[25%]', '[20%]', '[10%]'])
            self.assertNotIn('23/46', current)
            self.assertIn('<li title="产出概率20%。">', current)
            self.assertIn('<li title="产出概率10%。">', current)
            self.assertIn('[[中国光能工业公司 FZP 织物|中国光能工业公司 FZP 织物]]', current)


    def test_three_brands_keep_six_sections_and_named_bindings(self):
        entities=identity_catalog.read_json(ROOT/'data/equipment/records.json')['entities']
        for title, ordinary, named in [('5.11 Tactical', 14, 3), ('战队合金', 6, 2), ('中国光能工业公司', 9, 1)]:
            raw = source_for(title).read_text('utf-8')
            identity=re.search(r'\|资料ID=([^\n|}]+)',raw)[1].strip()
            collections=entities[identity]['collections']
            rendered = self.wiki.expand(raw, {})
            self.assertEqual(rendered.count('id="gear-'), 6)
            self.assertEqual(rendered.count('id="named-'), named)
            self.assertEqual(sum(len(value['rows']) for key,value in collections.items() if key.endswith('型号资料')), ordinary)
            self.assertEqual(len(collections['具名装备资料']['rows']),named)
            for section in ('套装加成', '装备属性', '具名装备', '制作与获取', '分解产物', '专精'):
                self.assertIn(section, rendered)
            self.assertNotIn('品牌材料名称待填写', rendered)
            self.assertNotIn('td2-data-error', rendered)
        for title,talent in [('战队合金','perfect_obliterate'),('中国光能工业公司','perfect_shock_and_awe')]:
            entity=next(e for e in entities.values() if e['page_title']=='品牌套装-'+title)
            self.assertIn(talent,[r.get('天赋引用') for r in entity['collections']['具名装备资料']['rows']])


if __name__ == '__main__':
    unittest.main()
