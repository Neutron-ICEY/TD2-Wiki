from tools import identity as identity_catalog
import copy
import json
from pathlib import Path
import unittest
import subprocess
import tempfile

from tools.asset_import.text_evidence import native_definitions
from tools.brand_sets.native_structure import StructureReader, attribute_categories, minor_count, mod_count, project_fields
from tools.brand_sets.equipment import resolve_equipment
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'tests/fixtures/named-structures.json').read_text('utf-8'))
CATEGORIES = attribute_categories(native_definitions(FIXTURE['attribute_dictionary'].encode(), include_data=True, include_objects=True))


class NamedStructureTests(unittest.TestCase):
    def test_all_current_named_pages_render_the_audited_structure(self):
        result = subprocess.run(['node', 'tools/brand_sets/navbox-records.cjs'], cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', check=True)
        pages = json.loads(result.stdout)['pages']
        expected = {row['stable_id']: row for row in FIXTURE['records']}
        wiki = WikiSubset(ROOT)
        seen = set()
        for page in pages:
            for params in page['named']:
                target = expected[params['stable_id']]
                seen.add(params['stable_id'])
                card = wiki.template('品牌装备摘要', params)
                with self.subTest(name=target['name']):
                    self.assertEqual(card.count('次属性：</span>'), max(1, target['minor_attribute_slots']))
                    self.assertEqual(card.count('插件槽：</span>'), max(1, target['mod_slot_count']))
                    if not target['mod_slot_count']:
                        self.assertIn('无插件槽位', card)
        self.assertEqual(seen, set(expected))

    def test_saved_native_standard_and_special_structures(self):
        for sample in FIXTURE['native_samples']:
            for kind, counter, key in [('minor', minor_count, 'minor_attribute_slots'), ('mod', mod_count, 'mod_slot_count')]:
                with self.subTest(name=sample['name'], kind=kind):
                    parsed = native_definitions(sample[kind]['raw'].encode(), include_data=True, include_objects=True)
                    kwargs = {'categories': CATEGORIES} if kind == 'minor' else {}
                    self.assertEqual(counter(parsed['resources'][0], parsed['links'], **kwargs), sample[key])

    def test_talent_parameter_is_not_a_minor_but_fixed_and_zero_presets_are(self):
        sample = next(row for row in FIXTURE['native_samples'] if row['name'] == '木匠')
        parsed = native_definitions(sample['minor']['raw'].encode(), include_data=True, include_objects=True)
        record = parsed['resources'][0]
        self.assertEqual(minor_count(record, parsed['links'], categories=CATEGORIES), 2)
        talent_uid = '3797E3755B885C61000239B175F90E8D'
        self.assertEqual(CATEGORIES[talent_uid], 'Talent_Parameters_Chest')
        fixed_uid = '4F5DDEA25284F3E00000062692378107'
        for preset in (fixed_uid, '0' * 32):
            changed = native_definitions(sample['minor']['raw'].replace(talent_uid, preset).encode(),
                                         include_data=True, include_objects=True)
            self.assertEqual(minor_count(changed['resources'][0], changed['links'], categories=CATEGORIES), 3)
        with self.assertRaisesRegex(ValueError, 'ATTRIBUTE_SEMANTICS_UNKNOWN'):
            minor_count(record, parsed['links'])

    def test_item_config_join_uses_native_uids_and_rejects_unverified_binding(self):
        sample = next(row for row in FIXTURE['native_samples'] if row['name'] == '放轻松')
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist', prefix='named-structure-test-') as directory:
            root = Path(directory) / 'raw_files'
            root.mkdir()
            dictionary = root / 'rogue/game system data/juice/attribute/dictionary'
            dictionary.mkdir(parents=True)
            (dictionary / 'attributes.mdict').write_text(FIXTURE['attribute_dictionary'], encoding='utf-8')
            self.assertTrue(root.resolve().is_relative_to(ROOT / 'dist'))
            (root / 'item.mitem').write_text(sample['mod']['raw'], encoding='utf-8')
            (root / 'configs_gear_mask_code1_data23.mitemgenerationconfigs').write_text(sample['minor']['raw'], encoding='utf-8')
            parsed = native_definitions(sample['mod']['raw'].encode(), include_data=True, include_objects=True)
            item = parsed['resources'][0]
            link = next(row for row in parsed['links'] if row['field'] == 'myItemGenerationConfig')
            source = dict(uid=item['resource_uid'], internal_name=item['internal_name'], resource_file='item.mitem',
                          generation_binding=dict(shared_config_link_uid=link['target_uid'],
                          generation_context=dict(code_version=1, data_version=23),
                          binding_evidence=dict(resource_file='configs_gear_mask_code1_data23.mitemgenerationconfigs')))
            reader = StructureReader(root)
            result = reader.structure(source)
            self.assertEqual((result['minor_attribute_slots'], result['mod_slot_count']), (1, 2))
            source['generation_binding']['shared_config_link_uid'] = '0' * 32
            with self.assertRaisesRegex(ValueError, 'CONFIG_IDENTITY'):
                reader.structure(source)

    def test_structure_reader_uses_dictionary_semantics_before_projecting_fields(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist', prefix='named-semantics-test-') as directory:
            root = Path(directory)
            raw = root / 'raw_files'
            dictionary = raw / 'rogue/game system data/juice/attribute/dictionary'
            dictionary.mkdir(parents=True)
            (dictionary / 'attributes.mdict').write_text(FIXTURE['attribute_dictionary'], encoding='utf-8')
            reader = StructureReader(root)
            for index, sample in enumerate(FIXTURE['native_samples']):
                path = raw / f'config{index}.mitemgenerationconfigs'
                path.write_text(sample['minor']['raw'], encoding='utf-8')
                record = reader.read(path)['resources'][0]
                minor, _ = reader.resolve(path, record['internal_name'], minor_count)
                self.assertEqual(minor, sample['minor_attribute_slots'], sample['name'])
                fields = project_fields(dict(minor_attribute_slots=minor, mod_slot_count=sample['mod_slot_count']),
                                        dict(minor_attribute_slots=2, mod_slot_count=1),
                                        {'次属性槽例外': '是', '次属性槽数': '3'})
                if minor == 2:
                    self.assertEqual(fields['次属性槽例外'], '否')
                    self.assertNotIn('次属性槽数', fields)

    def test_missing_is_not_zero_and_invalid_counts_do_not_inherit(self):
        self.assertIsNone(minor_count({'properties': []}, []))
        self.assertIsNone(mod_count({'properties': []}, []))
        self.assertEqual(minor_count({'properties': [], 'empty_blocks': [{'field': 'myAttributeSlots'}]}, []), 0)
        base = {'minor_attribute_slots': 2, 'mod_slot_count': 1}
        for value in (None, True, -1):
            with self.assertRaises(ValueError):
                project_fields({'minor_attribute_slots': value, 'mod_slot_count': 2}, base, {})

    def test_projection_reader_and_resolver_keep_counts_independent(self):
        base = identity_catalog.read_json(ROOT / 'data/brand-sets/equipment-base-rules.json')
        wiki = WikiSubset(ROOT)
        for slot, minor, mods in [('mask', 2, 1), ('mask', 1, 2), ('chest', 2, 1), ('holster', 3, 0), ('mask', 0, 2), ('mask', 1, 0)]:
            with self.subTest(slot=slot, minor=minor, mods=mods):
                structure = dict(minor_attribute_slots=minor, mod_slot_count=mods)
                fields = project_fields(structure, base['部位'][slot], {})
                params = dict(fields, stable_id='test_structure', 装备名称='NON-GAME-FACT', 装备部位=slot,
                              talent_mode='none', 主核心组合='使用部位设置')
                resolved = resolve_equipment(base, {'默认允许主核心': 'blue'}, slot, params)
                self.assertEqual((resolved['minor_attribute_slots'], resolved['mod_slot_count']), (minor, mods))
                card = wiki.template('品牌装备摘要内容', params)
                for label, count, text in [('次属性', minor, '随机加成'), ('插件槽', mods, '装备改装槽位')]:
                    rows = [part for part in card.split('<div class="td2-equipment-row">') if label + '：</span>' in part]
                    self.assertEqual(sum(row.count(text) for row in rows), count)
                again = project_fields(structure, base['部位'][slot], fields)
                self.assertEqual(again, fields)

    def test_one_dimension_does_not_rewrite_the_other(self):
        base = {'minor_attribute_slots': 2, 'mod_slot_count': 1}
        source = {'简介': 'preserved', '次属性槽数': '9', '插件槽数': '9'}
        before = copy.deepcopy(source)
        self.assertEqual(project_fields({'minor_attribute_slots': 2, 'mod_slot_count': 0}, base, source),
                         {'简介': 'preserved', '次属性槽例外': '否', '插件槽例外': '是', '插件槽数': '0'})
        self.assertEqual(source, before)
