"""Approved Reader rules; synthetic edge cases remain independent of game facts."""
import copy
import unittest
from pathlib import Path
from tools.brand_sets.equipment import load_equipment, resolve_equipment
from tools.brand_sets.icons import material_row_source, mappings, resolver_source
from wiki_subset import WikiSubset
from reader_test_html import nodes

ROOT=Path(__file__).resolve().parents[1]

class ReaderFinalTests(unittest.TestCase):
    def setUp(self): self.base,self.ui=load_equipment(ROOT)

    def test_six_dismantle_combinations_and_amounts(self):
        weaves={'mask':'面具织物','backpack':'背包织物','chest':'胸甲织物','gloves':'手套织物','holster':'枪套织物','kneepads':'护膝织物'}
        for slot,weave in weaves.items():
            rule=self.base['部位'][slot]
            self.assertEqual(rule['minor_attribute_slots'],2)
            self.assertEqual(rule['base_armor'], {'mask':80297, 'chest':157961, 'backpack':130844, 'gloves':80297, 'holster':111889, 'kneepads':98726}[slot])
            self.assertEqual(rule['dismantle']['brand_material_amount'],{'min':1,'max':1})
            rows=rule['dismantle']['fixed_materials']
            self.assertEqual([r['name'] for r in rows],['防御性布料',weave])
            self.assertEqual([r['amount'] for r in rows],[{'min':23,'max':46},{'min':1,'max':1}])
            self.assertEqual(rows[0]['amount_values'],[23,46])
            output=WikiSubset(ROOT).template('TD2分解规则', {'1':slot})
            self.assertIn('23 / 46',output)
            self.assertNotIn('23–46',output)
            self.assertEqual(rows[0]['base_amount'],23)
            self.assertTrue(rows[0]['use_extra_quantity_bonus'])
            chance=rule['dismantle']['chance_materials']
            self.assertEqual([r['name'] for r in chance],['陶瓷碎片','聚碳酸酯'])
            self.assertEqual([r['amount'] for r in chance],[{'min':8,'max':8}]*2)
            self.assertEqual([r['chance_percent'] for r in chance],[20,10])
            self.assertEqual([r['requires_perk_level'] for r in chance],[2,2])

    def test_random_default_zero_exception_and_unknown_remain_distinct(self):
        wiki=WikiSubset(ROOT)
        common={'默认允许主核心':'blue'}
        self.assertEqual(resolve_equipment(self.base,common,'mask')['minor_attribute_slots'],2)
        override={'次属性槽例外':'是','次属性槽数':'0'}
        self.assertEqual(resolve_equipment(self.base,common,'mask',override)['minor_attribute_slots'],0)
        for slot in self.base['部位']:
            output=wiki.template('TD2普通装备规则',{'1':slot,'主属性':'blue'})
            self.assertEqual(output.count('随机加成'),2)
        zero=wiki.template('品牌次属性行',{'数量':'0'})
        self.assertIn('无次属性槽位',zero)
        self.assertNotIn('随机加成',zero)
        unknown=wiki.template('品牌次属性行',{'数量':''})
        self.assertIn('未配置／待核实',unknown)
        invalid=wiki.template('品牌次属性行',{'数量':'2','固定次属性':'NON_GAME_FACT_INVALID'})
        self.assertIn('未知固定词条预设',invalid)
        fixture=WikiSubset(ROOT,sources={
            'wiki/templates/TD2固定词条图标.wiki':'<includeonly></includeonly>',
            'wiki/templates/TD2固定词条片段.wiki':'<includeonly>NON-GAME-FACT fixed bonus</includeonly>'})
        fixed=fixture.template('品牌次属性行',{'数量':'2','固定次属性':'fixed_minor_fixture'})
        self.assertEqual(fixed.count('NON-GAME-FACT fixed bonus'),1)
        self.assertEqual(fixed.count('随机加成'),1)

    def test_material_links_alias_and_missing_image(self):
        files=['File:'+v['wiki_file'] for v in mappings(self.ui).values() if v['wiki_file']]
        wiki=WikiSubset(ROOT,files)
        args={'名称':'面具织物','材料ID':'weave_mask','数量':'0–1'}
        weave=wiki.template('TD2材料行',args)
        self.assertIn('[[材料-面具织物|面具织物]]',weave);self.assertIn('0–1',weave)
        self.assertIn('File:'+self.ui['material_icons']['weave_mask']['wiki_file'],weave)
        absent=WikiSubset(ROOT).template('TD2材料行',args)
        self.assertIn('[[File:'+self.ui['material_icons']['weave_mask']['wiki_file']+'|',absent)
        self.assertNotIn('td2-icon-placeholder',absent)
        self.assertEqual([n.text for n in nodes(absent,'td2-material-name')],[n.text for n in nodes(weave,'td2-material-name')])
        alias=wiki.template('TD2材料行',{'名称':'防御性布料','材料ID':'protective_fabric','数量':'23 / 46'})
        self.assertIn('[[材料-防具布料|防御性布料]]',alias);self.assertIn('|link=材料-防具布料|',alias)

    def test_icon_resolver_has_one_size_and_optional_link(self):
        source=resolver_source(mappings(self.ui))
        self.assertNotIn('16x16px',source)
        self.assertNotIn('40x40px',source)
        self.assertIn('24x24px|link={{{链接|}}}',source)
        self.assertIn('TD2-UI-None-Icon.png',source)
        self.assertNotIn('➖',source)
        state = WikiSubset(ROOT).template('TD2图标', {'类别':'state','键':'none'})
        self.assertIn('[[File:TD2-UI-None-Icon.png|', state)
        self.assertNotIn('⊘',state)
        self.assertIn('⊘', resolver_source({'state/none': {'wiki_file': ''}}))

if __name__=='__main__':unittest.main()
