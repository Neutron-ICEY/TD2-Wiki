from pathlib import Path
import unittest

from tools.brand_sets.build import GENERATED
from tools.brand_sets.equipment import load_equipment, resolve_equipment, validate_equipment_fields
from tools.brand_sets.equipment_projection import equipment_sources
from tools.brand_sets.slots import SLOTS
from wiki_subset import WikiSubset


ROOT = Path(__file__).resolve().parents[1]


class TalentSlotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.ui = load_equipment(ROOT)
        cls.sources = equipment_sources(cls.base, cls.ui, include_resolver=False)
        cls.wiki = WikiSubset(ROOT, sources=cls.sources)

    def test_domain_accepts_only_matching_random_talent_slots(self):
        for slot in SLOTS:
            for mode in ('none', 'fixed', 'random_chest', 'random_backpack'):
                params = {'装备部位': slot, 'talent_mode': mode}
                with self.subTest(slot=slot, mode=mode):
                    if mode.startswith('random_') and mode != 'random_' + slot:
                        with self.assertRaisesRegex(ValueError, '随机天赋类型与装备部位不符'):
                            validate_equipment_fields(params)
                        with self.assertRaisesRegex(ValueError, '随机天赋类型与装备部位不符'):
                            resolve_equipment(self.base, {}, slot, params)
                    else:
                        validate_equipment_fields(params)
                        resolve_equipment(self.base, {}, slot, params)

    def test_reader_rejects_conflicts_without_rendering_an_attribute_card(self):
        for slot in SLOTS:
            for mode in ('', 'none', 'fixed', 'random_chest', 'random_backpack'):
                with self.subTest(slot=slot, mode=mode):
                    output = self.wiki.template('TD2普通装备规则', {'1': slot, 'talent_mode': mode})
                    invalid = mode.startswith('random_') and mode != 'random_' + slot
                    self.assertEqual('随机天赋类型与装备部位不符' in output, invalid)
                    self.assertEqual('class="td2-equipment-attributes"' in output, not invalid)

    def test_named_reader_uses_the_same_guard(self):
        output = self.wiki.template('品牌装备摘要内容', {'stable_id': 'test_conflict', '装备名称': 'NON-GAME-FACT',
                                                  '装备部位': 'gloves', 'talent_mode': 'random_backpack'})
        self.assertIn('随机天赋类型与装备部位不符', output)
        self.assertNotIn('class="td2-equipment-attributes"', output)
        self.assertNotIn('随机背包天赋槽位', output)

    def test_registered_rule_matches_the_generator(self):
        path = GENERATED['equipment-base-rules']
        self.assertEqual((ROOT / path).read_text(encoding='utf-8'), self.sources[path])


if __name__ == '__main__':
    unittest.main()
