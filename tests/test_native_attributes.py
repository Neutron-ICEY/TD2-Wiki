from tools import identity as identity_catalog
import json
import unittest
from pathlib import Path
from tools.equipment.native_attributes import constant_value

ROOT=Path(__file__).resolve().parents[1]

class PublicAttributeRulesTests(unittest.TestCase):
    def test_constant_high_level_interval_does_not_assume_a_power_endpoint(self):
        curve={'brackets':[dict(max_power=930,a='0',b='.000035',c='.01'),dict(max_power=3777,a='0',b='0',c='.05'),dict(max_power=-1,a='0',b='0',c='.05')], 'qualities':{'Orange':'1.6'}}
        self.assertEqual(constant_value(curve,'Orange','Percentage',930),'8')
        curve['brackets'][1]['b']='.01'
        with self.assertRaisesRegex(ValueError,'Power'):constant_value(curve,'Orange','Percentage',930)
        curve['brackets'][1]['b']='0';curve['brackets'][2]['c']='.06'
        with self.assertRaisesRegex(ValueError,'differ'):constant_value(curve,'Orange','Percentage',930)

    def test_public_identities_aliases_and_limited_value_scope(self):
        data=identity_catalog.read_json(ROOT/'data/equipment/attributes.json')
        identities=data['identities'];self.assertEqual(len(identities),33);self.assertEqual(len({v['native_uid'] for v in identities.values()}),32)
        self.assertEqual(sorted(v['display_alias'] for v in identities.values() if 'display_alias' in v),sorted(['技能修复','暴击几率','武器控制']))
        self.assertEqual(len(data['native_profile']['constant_rules']),10)
        self.assertNotIn('fixed_minor_claws_out_melee_damage',[r['id'] for r in data['native_profile']['constant_rules']])
        minor=identity_catalog.read_json(ROOT/'data/brand-sets/minor-attributes.json')
        for row in minor['attributes']+data['core_attributes']:
            self.assertEqual(row['zh_name'],identities[row['id']].get('display_alias',identities[row['id']]['zh_name']))
            self.assertEqual(row['unit_type'],identities[row['id']]['unit_type'])
