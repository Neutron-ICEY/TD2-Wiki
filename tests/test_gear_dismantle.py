from tools import identity as identity_catalog
import json
import unittest
from pathlib import Path

from tools.brand_sets.equipment import dismantle_entries, load_equipment
from tools.brand_sets.equipment_projection import equipment_sources, gear_dismantle_base
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class GearDismantleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = identity_catalog.read_json(ROOT / 'data/gear-sets/sets.json')['sets']
        cls.shared = identity_catalog.read_json(ROOT / 'data/gear-sets/dismantle-rules.json')
        cls.base, cls.ui = load_equipment(ROOT)
        cls.view = WikiSubset(ROOT, existing_files=['File:TD2-GearSet-MeasuredAssembly-Logo.png'])

    def entity(self, title):
        return next(s for s in self.catalog if s['title'] == title)

    def test_all_sets_share_confirmed_common_outputs_and_native_probabilities(self):
        expected = {'防御性布料': 23, '陶瓷碎片': 10, '聚碳酸酯': 10, '碳纤维': 4, '电子元件': 4, '钛合金': 4}
        self.assertEqual(len(self.catalog), 30)
        for item in self.catalog:
            self.assertNotIn('common', item['dismantle'])
            self.assertNotIn('slots', item['dismantle'])
            base = gear_dismantle_base(item, self.shared)
            for slot in self.shared['slots']:
                rows = dismantle_entries(base, '', slot, self.ui)
                for name, quantity in expected.items():
                    row = next(r for r in rows if r['name'] == name)
                    self.assertEqual(row['amount'], {'min': quantity, 'max': quantity})
                self.assertEqual(len(rows), 7)
                weave = next(r for r in rows if r.get('id') == 'weave_' + slot)
                self.assertEqual(weave['amount'], {'min': 1, 'max': 1})
        chances = self.shared['common']['chance_materials']
        self.assertEqual([r['chance_percent'] for r in chances], [20, 10])
        self.assertTrue(all(r['requires_perk_level'] == self.shared['dismantle_profile']['perk_level'] for r in chances))
        self.assertTrue(all(r['probability_source'] == 'native_definition_not_gameplay_frequency' for r in chances))

    def test_ongoing_directive_quantities_and_six_part_identity(self):
        item = self.entity('政令进行式')
        for slot in self.shared['slots']:
            out = self.view.template('TD2分解规则', {'1': slot, '装备组': item['id'], '品牌材料': item['material']['name'], '品牌': item['id']})
            self.assertEqual(out.count('class="td2-material-row '), 8)
            self.assertIn('0 / 10', out)
            self.assertIn('20%', out)
            self.assertIn('10%', out)
            self.assertIn('政令进行式材料', out)
            self.assertNotIn('数量待核实', out)
            self.assertNotIn('46', out)

    def test_specific_native_two_is_preserved_instead_of_defaulting_to_one(self):
        expected = ['谈判者困境', '先锋部队', 'A、8 两对', '铸造厂堡垒', '未来主动权']
        for title in expected:
            item = self.entity(title)
            self.assertEqual(item['dismantle']['brand_material_amount'], {'min': 2, 'max': 2})
            self.assertTrue(item['dismantle']['material_rule']['required_tag'].startswith('Economy_GearSet_'))
            base = gear_dismantle_base(item, self.shared)
            row = next(r for r in dismantle_entries(base, item['material']['name'], 'mask', self.ui) if r.get('brand'))
            self.assertEqual(row['amount']['min'], 2)

    def test_empty_specific_material_keeps_common_outputs_known(self):
        for title in ['固线链接', '精密组件', '政令进行式', '谈判者困境']:
            item = self.entity(title)
            for slot in self.shared['slots']:
                for value in [None, '', ' \n ']:
                    args = {'1': slot, '装备组': item['id'], '品牌': item['id']}
                    if value is not None:
                        args['品牌材料'] = value
                    out = self.view.template('TD2分解规则', args)
                    self.assertEqual(out.count('class="td2-material-row '), 7)
                    self.assertEqual(out.count('<li'), 7)
                    self.assertNotIn('数量待核实', out)
                    self.assertIn('钛合金', out)
                    self.assertNotIn('td2-material-gear_set', out)

    def test_measured_material_user_confirmation_and_existing_icon(self):
        item = self.entity('精密组件')
        self.assertEqual(item['material']['currency_uid'], 'B005013567F7BF9E0003777B0F3916AD')
        self.assertEqual(item['material']['name'], '精密组件材料')
        self.assertIsNone(self.entity('固线链接').get('material'))
        for slot in self.shared['slots']:
            out = self.view.template('TD2分解规则', {'1': slot, '装备组': item['id'], '品牌材料': '精密组件材料', '品牌': item['id']})
            self.assertEqual(out.count('class="td2-material-row '), 8)
            self.assertIn('td2-material-row td2-material-gear_set', out)
            self.assertIn('File:TD2-GearSet-MeasuredAssembly-Logo.png', out)
            self.assertEqual(out.count('td2-material-quantity">1<'), 2)

    def test_brand_profile_and_projection_keep_existing_business_rules(self):
        self.assertEqual(self.base['dismantle_profile']['quality'], 'Orange')
        self.assertEqual(self.base['部位']['mask']['dismantle']['chance_materials'][0]['amount']['min'], 8)
        source = equipment_sources(self.base, self.ui)['wiki/templates/TD2分解规则.wiki']
        self.assertIn('23 / 46', source)
        self.assertIn('0 / 8', source)
        self.assertNotIn('0 / 10', source)

    def test_shared_generation_and_empty_placeholder_contract(self):
        source = equipment_sources(self.base, self.ui, gear_sets=self.catalog)['wiki/templates/TD2分解规则.wiki']
        self.assertEqual(source, (ROOT / 'wiki/templates/TD2分解规则.wiki').read_text(encoding='utf8'))
        unknown = self.view.template('TD2图标', {'类别': 'talent', '键': 'unmapped_gear'})
        self.assertIn('td2-icon-placeholder', unknown)
        self.assertNotIn('state/unknown', unknown)
        key = 'gear_effect:z_c487423d6998214200037c60dd862516'
        core = WikiSubset(ROOT,existing_files=['File:TD2-Talent-GearSet-CoreStrength-SharedEffects-Icon.png']).template('TD2图标', {'类别': 'talent', '键': key})
        self.assertIn('File:TD2-Talent-GearSet-CoreStrength-SharedEffects-Icon.png', core)
        self.assertNotIn('td2-icon-placeholder', core)
