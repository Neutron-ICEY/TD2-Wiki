"""Approved M01 values; independent expectations and real template projections."""
import copy
import unittest
from pathlib import Path
from tools.brand_sets.equipment import load_equipment, resolve_equipment, EQUIPMENT_FIELDS
from tools.brand_sets.equipment_projection import equipment_sources, _armor_display
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'mask':80297, 'chest':157961, 'backpack':130844, 'gloves':80297, 'holster':111889, 'kneepads':98726}

DISPLAY = {'mask':'80.3K', 'chest':'158.0K', 'backpack':'130.8K', 'gloves':'80.3K', 'holster':'111.9K', 'kneepads':'98.7K'}

class ArmorM01Tests(unittest.TestCase):
    def setUp(self):
        self.base, self.ui = load_equipment(ROOT)
        self.wiki = WikiSubset(ROOT)

    def test_values_and_total(self):
        self.assertEqual({k:v['base_armor'] for k,v in self.base['部位'].items()}, EXPECTED)
        self.assertEqual(sum(EXPECTED.values()), 660014)
        self.assertNotIn(170000, EXPECTED.values())


    def test_null_zero_and_single_source_projection(self):
        base = copy.deepcopy(self.base)
        for value, display in ((None,'待核实'), (0,'0.0K'), (123456,'123.5K')):
            base['部位']['mask']['base_armor'] = value
            wiki = WikiSubset(ROOT, sources=equipment_sources(base,self.ui))
            self.assertIn('基础装甲：'+display, wiki.template('TD2普通装备规则',{'1':'mask'}))
        self.assertNotIn('base_armor', EQUIPMENT_FIELDS)
        self.assertNotIn('基础装甲', EQUIPMENT_FIELDS)

    def test_other_facts_sentinel_preserved(self):
        sentinel = 'NON-GAME-FACT M01 Sentinel 其他事实资料'
        text = self.wiki.template('品牌套装内容', {'套装全称':'NON-GAME-FACT', '其他机制':sentinel})
        self.assertEqual(text.count(sentinel), 1)

    def test_display_rounding_and_invalid_values(self):
        for value, display in ((1250,'1.3K'), (1249,'1.2K'), (1000,'1.0K'), (999950,'1000.0K')):
            self.assertEqual(_armor_display(value),display)
        for value in (None, True, False, -1, '80297', 80297.0, float('nan'), float('inf')):
            self.assertEqual(_armor_display(value),'待核实')
        self.assertNotIn('（40级）', (ROOT/'wiki/templates/品牌装备属性.wiki').read_text(encoding='utf-8'))
