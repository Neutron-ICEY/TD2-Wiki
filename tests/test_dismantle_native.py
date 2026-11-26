import copy
import unittest
from pathlib import Path

from current_identity import material_id
from tools.brand_sets.build import GENERATED
from tools.brand_sets.equipment import dismantle_amount_text, dismantle_materials, dismantle_note, dismantle_probability_text, load_equipment, validate_base
from tools.brand_sets.equipment_projection import equipment_sources
from tools.publish.bundle import PublishError


ROOT = Path(__file__).resolve().parents[1]


class NativeDismantleTests(unittest.TestCase):
    def setUp(self):
        self.base, self.ui = load_equipment(ROOT)

    def test_observed_discrete_outputs_do_not_become_a_continuous_range(self):
        material = self.base['部位']['mask']['dismantle']['fixed_materials'][0]
        self.assertEqual(material['amount'], {'min': 23, 'max': 46})
        self.assertEqual(material['amount_values'], [23, 46])
        self.assertEqual(material['base_amount'], 23)
        self.assertEqual(dismantle_amount_text(material), '23 / 46')
        self.assertEqual(dismantle_probability_text(self.base, material), '25%')
        self.assertEqual(dismantle_note(self.base, material), '额外产出概率25%。')
        unknown = copy.deepcopy(material)
        unknown.pop('amount_values')
        unknown['amount'] = {'min': None, 'max': None}
        self.assertEqual(dismantle_amount_text(unknown), '数量待核实')
        self.assertEqual(dismantle_probability_text(self.base, unknown), '25%')
        source = equipment_sources(self.base, self.ui)[GENERATED['equipment-dismantle']]
        self.assertIn('<li title="额外产出概率25%。">{{TD2材料行|名称=防御性布料|材料ID=protective_fabric|数量=23 / 46|概率说明=25%}}', source)
        self.assertNotIn('23/46', source)
        self.assertNotIn('23–46', source)
        self.assertNotIn('21–24', source)
        changed = copy.deepcopy(self.base)
        changed['部位']['mask']['dismantle']['fixed_materials'][0]['amount'] = {'min': 0, 'max': 0}
        with self.assertRaises(PublishError):
            validate_base(changed)

    def test_discrete_values_must_match_bounds_and_preserve_zero(self):
        for values in ([46, 23], [23, 23, 46], [True, 46], [], [23, 47]):
            changed = copy.deepcopy(self.base)
            changed['部位']['mask']['dismantle']['fixed_materials'][0]['amount_values'] = values
            with self.subTest(values=values), self.assertRaises(PublishError):
                validate_base(changed)
        self.assertEqual(dismantle_amount_text({'amount': {'min': 0, 'max': 1}, 'amount_values': [0, 1]}), '0 / 1')
        self.assertEqual(dismantle_amount_text({'amount': {'min': 8, 'max': 8}, 'amount_values': [8], 'chance_percent': 20}), '0 / 8')
        self.assertEqual(dismantle_amount_text({'amount': {'min': 0, 'max': 8}, 'amount_values': [0, 8], 'chance_percent': 20}), '0 / 8')

    def test_fixed_and_probability_outputs_remain_distinct(self):
        rows = dismantle_materials(self.base, '耶尔装甲合成“羽毛”', 'mask', self.ui)
        self.assertEqual(rows, [('防御性布料', '23 / 46'), ('陶瓷碎片', '0 / 8'), ('聚碳酸酯', '0 / 8'), ('面具织物', '1'), ('耶尔装甲合成“羽毛”', '1')])
        self.assertEqual(dismantle_materials(self.base, '', 'mask', self.ui), [row for row in rows if row[0] != '耶尔装甲合成“羽毛”'])
        self.assertEqual(dismantle_amount_text({'amount': {'min': 0, 'max': 0}}), '0')
        self.assertEqual(dismantle_probability_text(self.base, {'chance_percent': 100}), '')
        for material in self.base['部位']['mask']['dismantle']['chance_materials']:
            self.assertEqual(dismantle_note(self.base, material), f'产出概率{material["chance_percent"]}%。')
        source = equipment_sources(self.base, self.ui)[GENERATED['equipment-dismantle']]
        self.assertNotIn('（固定）', source)
        self.assertNotIn('<small>', source)
        self.assertIn('<li title="产出概率20%。">{{TD2材料行|名称=陶瓷碎片|材料ID=ceramics|数量=0 / 8|概率说明=20%}}', source)
        self.assertIn('<li title="产出概率10%。">{{TD2材料行|名称=聚碳酸酯|材料ID=polycarbonate|数量=0 / 8|概率说明=10%}}', source)
        self.assertNotIn('|概率说明=100%', source)

    def test_quality_order_includes_blue_when_present(self):
        changed = copy.deepcopy(self.base)
        changed['部位']['mask']['dismantle']['fixed_materials'].insert(0, {'id':'electronics','name': '电子元件', 'amount': {'min': 1, 'max': 1}})
        rows = dismantle_materials(changed, '耶尔装甲合成“羽毛”', 'mask', self.ui)
        self.assertEqual([self.ui['material_display'][material_id(name)]['quality'] for name, _ in rows], ['gray', 'green', 'green', 'blue', 'high_end', 'high_end'])
        source = equipment_sources(changed, self.ui)[GENERATED['equipment-dismantle']]
        self.assertLess(source.index('名称=聚碳酸酯'), source.index('名称=电子元件'))
        self.assertLess(source.index('名称=电子元件'), source.index('名称={{{品牌材料|}}}'))

    def test_only_supported_profile_is_presented(self):
        source = equipment_sources(self.base, self.ui)[GENERATED['equipment-dismantle']]
        self.assertIn('|scope=满级拆解专长；无活动倍率\n', source)
        for filename in ('品牌套装信息.wiki', '装备组信息.wiki'):
            self.assertNotIn('{{TD2分解规则|scope}}', (ROOT / 'wiki/templates' / filename).read_text('utf-8'))
        changed = copy.deepcopy(self.base)
        changed['dismantle_profile']['perk_level'] = 1
        with self.assertRaises(PublishError):
            validate_base(changed)

    def test_probability_cannot_be_listed_as_fixed(self):
        changed = copy.deepcopy(self.base)
        rule = changed['部位']['mask']['dismantle']
        rule['fixed_materials'].append(rule['chance_materials'].pop())
        with self.assertRaises(PublishError):
            validate_base(changed)
        changed = copy.deepcopy(self.base)
        changed['部位']['mask']['dismantle']['chance_materials'][0]['chance_percent'] = 100
        with self.assertRaises(PublishError):
            validate_base(changed)

    def test_six_slots_share_common_pool_and_keep_distinct_weaves(self):
        common = None
        for slot, rule in self.base['部位'].items():
            rows = dismantle_materials(self.base, '', slot, self.ui)
            names = [name for name, amount in rows]
            self.assertNotIn('碳纤维', names)
            self.assertNotIn('电子元件', names)
            self.assertEqual(rule['dismantle']['fixed_materials'][1]['id'], 'weave_' + slot)
            with_brand = dismantle_materials(self.base, '耶尔装甲合成“羽毛”', slot, self.ui)
            self.assertEqual([name for name, _ in with_brand[-2:]], [rule['dismantle']['fixed_materials'][1]['name'], '耶尔装甲合成“羽毛”'])
            current = [row for row in rows if row[0] != rule['dismantle']['fixed_materials'][1]['name']]
            if common is None:
                common = current
            self.assertEqual(current, common)


if __name__ == '__main__':
    unittest.main()
