import json
from pathlib import Path
import tempfile
import unittest
from tools.asset_import.text_evidence import native_definitions
from tools.equipment.native import Native
from tools.equipment.rules import EquipmentRules

ROOT=Path(__file__).resolve().parents[1]

class EquipmentRulesTests(unittest.TestCase):
    def test_partial_model_failure_keeps_that_field_and_does_not_block_resolved_fields(self):
        from unittest.mock import patch
        rules=EquipmentRules(Native(ROOT/'tests/fixtures/equipment-native'))
        entity={'id':'TEST','template':'品牌套装信息','bindings':[{'source':'fixture.mitem','uid':str(i),'records':[{'field':'mask型号资料','id':{'装备UID':str(i)}}],'fields':{'中文名称':{'property':'myUIName'}}} for i in range(2)]}
        core={'count':1,'selection':'fixed','types':['blue']}
        with patch.object(rules,'item',side_effect=[('mask',{'core':core,'minor_count':2,'mods':1},{}),('mask',{'core':core,'minor_count':None,'mods':1},{'minor_count':'missing definition'})]):
            units,missing=rules.project(entity)
            self.assertEqual({u['target']['field'] for u in units},{'core','mods'})
            self.assertEqual(missing[0]['reason'],'missing definition')
        with patch.object(rules,'item',side_effect=[('mask',{'core':core,'minor_count':2,'mods':1},{}),ValueError('missing item')]):
            units,missing=rules.project(entity)
            self.assertEqual(units,[])
            self.assertEqual(missing[0]['reason'],'missing item')

    def test_actual_configs_keep_core_count_candidates_and_selection_independent(self):
        fixture=json.loads((ROOT/'tests/fixtures/core-configs.json').read_text('utf8'))
        with tempfile.TemporaryDirectory(dir=ROOT/'dist') as temporary:
            path=Path(temporary)/'pool.mitemgenerationattributelists';path.write_text(fixture['pool'],encoding='utf8')
            rules=EquipmentRules(Native(Path(temporary)))
            for row in rules.reader.read(path)['resources']:
                rules.pools[row['resource_uid']]=(path,row['internal_name'])
            for sample in fixture['samples']:
                with self.subTest(name=sample['name']):
                    parsed=native_definitions(sample['raw'].encode(),include_data=True,include_objects=True)
                    record=parsed['resources'][0]
                    result=rules.core(sample['quality'])(record,parsed['links'])
                    self.assertEqual(result,{'count':1 if sample['name']=='投资者' else 3,'selection':'random' if sample['name']=='投资者' else 'fixed','types':['red','blue','yellow']})

    def test_incomplete_pvp_override_does_not_use_pve(self):
        native=Native(ROOT/'tests/fixtures/equipment-native')
        row=native.record('hunter/game system data/juice/item/gear_brand_set_511.mgearset','4CDCE5B25C405137000321F5482F6F7B')
        row['properties']=[p for p in row['properties'] if not(p['field']=='myValue' and any(c['resource_type']=='GearSetEffectOverride' for c in p['context']))]
        with self.assertRaisesRegex(ValueError,'override incomplete'):
            native.bonus(row,'5D31260055F145480000064D6A3B97D0',1,'PvP')

    def test_invalid_pvp_text_does_not_fall_back_to_pve(self):
        native=Native(ROOT/'tests/fixtures/equipment-native')
        row=native.record('hunter/game system data/juice/talent/talent_gearset_negotiatorsdilemma_6piece.mtalent','346395BC5C94D0FD000631CADE63B7A1')
        pve=native.talent(row,'PvE')
        prop=next(p for p in row['fields'] if p['field']=='myOverrideToolTipText')
        prop['guid']='unavailable localization'
        with self.assertRaises(KeyError):native.talent(row,'PvP')
        self.assertEqual(native.talent(row,'PvE'),pve)
