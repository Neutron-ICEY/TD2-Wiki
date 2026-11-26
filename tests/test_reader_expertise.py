"""M02/M03: public expertise contract and legacy consumers."""
import copy
import re
import unittest
from pathlib import Path
from tools.brand_sets.equipment import load_equipment, validate_base, EQUIPMENT_FIELDS
from tools.brand_sets.equipment_projection import equipment_sources, _expertise_card
from wiki_subset import WikiSubset
ROOT = Path(__file__).resolve().parents[1]
class ExpertiseTests(unittest.TestCase):
    def setUp(self):
        self.base,self.ui=load_equipment(ROOT)
    def test_approved_values(self):
        self.assertEqual(self.base['expertise'], {'armor_bonus_per_level_percent':1,'max_level':30})
        self.assertEqual(sum(r['base_armor'] for r in self.base['部位'].values()),660014)
    def test_missing_legacy_and_invalid_contract(self):
        old=copy.deepcopy(self.base); del old['expertise']
        validate_base(old)
        self.assertEqual(_expertise_card(old),'')
        self.assertEqual(WikiSubset(ROOT,sources=equipment_sources(old,self.ui)).template('TD2普通装备规则',{'1':'expertise'}).strip(),'')
        for bad in (None,{},[],{'armor_bonus_per_level_percent':1}, {'armor_bonus_per_level_percent':True,'max_level':30}, {'armor_bonus_per_level_percent':'1','max_level':30}, {'armor_bonus_per_level_percent':1,'max_level':0}, {'armor_bonus_per_level_percent':-1,'max_level':30}, {'armor_bonus_per_level_percent':1,'max_level':30,'extra':1}):
            base=copy.deepcopy(self.base);base['expertise']=bad
            with self.subTest(bad=bad),self.assertRaisesRegex(ValueError,'expertise'):validate_base(base)
    def test_single_card_and_order(self):
        wiki=WikiSubset(ROOT)
        for mode in ('PvE','PvP'):
            text=wiki.template('品牌套装内容',{'套装全称':'NON-GAME-FACT','模式':mode,'其他机制':'NON-GAME-FACT Sentinel'})
            self.assertEqual(text.count('class="td2-expertise-card"'),1)
            self.assertLess(text.rindex('class="td2-materials"'),text.index('class="td2-expertise-card"'))
            self.assertLess(text.index('class="td2-expertise-card"'),text.index('其他资料'))
            self.assertEqual(text.count('NON-GAME-FACT Sentinel'),1)
            self.assertIn('<strong>+1%</strong>',text);self.assertIn('30级',text)
            self.assertNotIn('了解专精系统',text)
            self.assertNotIn('td2-expertise-stats',text)
            self.assertNotIn('装备通用规则',text)
            self.assertNotIn('每提升一级增加',text)
            self.assertNotIn('适用于40级的六个装备部位',text)
            self.assertNotIn('适用于精通的装备',text)
            self.assertNotIn('30级别',text)
            card = wiki.template('TD2普通装备规则', {'1':'expertise'})
            self.assertTrue(card.startswith('<h2 class="td2-expertise-title">专精</h2>'))
            self.assertIn('<h2 class="td2-expertise-title">专精</h2>', _expertise_card(self.base))
            self.assertNotIn('td2-divider-soft',card)
            self.assertNotIn('<section',card)
            self.assertEqual(card.count('class="td2-equipment-row"'),2)
            self.assertEqual(card.count('class="td2-row-label"'),2)
            self.assertIn('每级加成：</span>',card)
            self.assertIn('<strong>+1%</strong> 装甲',card)
        self.assertNotIn('expertise',EQUIPMENT_FIELDS)
    def test_single_source_and_legacy_note(self):
        base=copy.deepcopy(self.base)
        base['expertise']={'armor_bonus_per_level_percent':2,'max_level':31}
        base['部位']['mask']['specialization_note']='NON-GAME-FACT legacy note'
        wiki=WikiSubset(ROOT,sources=equipment_sources(base,self.ui))
        card=wiki.template('TD2普通装备规则',{'1':'expertise'})
        self.assertIn('+2%',card);self.assertIn('31级',card);self.assertIn('等级上限',card)
        self.assertEqual(card.strip(),wiki.expand(_expertise_card(base, wiki=True), {}).strip())
        slot=wiki.template('TD2普通装备规则',{'1':'mask'})
        self.assertIn('NON-GAME-FACT legacy note',slot)
        self.assertNotIn('td2-expertise-card',slot)
        self.assertNotIn('legacy note',card)
    def test_css_only_targets_card(self):
        css=(ROOT/'ui/brand-sets/brand-sets.css').read_text(encoding='utf-8')
        rules=re.findall(r'([^{}]+)\{([^{}]*)\}',re.sub(r'/\*.*?\*/','',css,flags=re.S))
        selected=[(selector.strip(),body) for selector,body in rules if '.td2-expertise-' in selector]
        self.assertTrue(selected)
        for selector,body in selected:
            # Commas in :is() separate alternatives within a single scoped selector.
            for part in re.split(r',(?![^()]*\))', selector):
                if '.td2-expertise-' in part:
                    self.assertRegex(part.strip(), r'^\.td2-(?:brand|weapons|gear-set|exotic-gear)\b', part)
            self.assertNotIn('filter:',body)
            self.assertNotIn('var(--td2-accent)',body)
        self.assertIn('color-mix(in srgb, #68a7db 50%, currentColor)', ''.join(body for _,body in selected))
