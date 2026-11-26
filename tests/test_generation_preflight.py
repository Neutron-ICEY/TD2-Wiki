import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.generation import apply, plan
from tools.brand_sets import build
from tools.equipment_attributes.catalog import load, ordinary_rows
from tools.brand_sets.fixed_minor import resolve

ROOT = Path(__file__).resolve().parents[1]


class GenerationPreflightTests(unittest.TestCase):
    def test_all_targets_owners_and_encodings_precede_writes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as temp:
            root = Path(temp)
            first, second = 'wiki/templates/first.wiki', 'wiki/templates/second.wiki'
            (root / first).parent.mkdir(parents=True)
            (root / first).write_text('original', encoding='utf8')
            sources = {first: 'updated', second: 'new'}
            registry = {'entries': [dict(source=s, title='Template:' + Path(s).stem, namespace=10, ownership='generated', generator='test') for s in sources]}
            owners = dict.fromkeys(sources, 'test')
            mutations = [lambda r: r['entries'][1].update(ownership='manual'),
                         lambda r: r['entries'].pop(),
                         lambda r: r['entries'].append(dict(r['entries'][1])),
                         lambda r: r['entries'][1].update(generator='other'),
                         lambda r: r['entries'][1].update(title=r['entries'][0]['title'])]
            for mutate in mutations:
                broken = copy.deepcopy(registry)
                mutate(broken)
                with self.assertRaises(ValueError):
                    apply(plan(root, sources, broken, owners))
                self.assertEqual((root / first).read_text(encoding='utf8'), 'original')
                self.assertFalse((root / second).exists())
            with self.assertRaises(UnicodeError):
                apply(plan(root, {first: 'updated', second: '\ud800'}, registry, owners))
            (root / second).mkdir()
            with self.assertRaises(ValueError):
                apply(plan(root, sources, registry, owners))
            self.assertEqual((root / first).read_text(encoding='utf8'), 'original')

    def test_brand_navbox_input_failure_does_not_write_earlier_helpers(self):
        original = build.derived_sources
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            first = next(iter(result))
            result[first] += '\nNON-GAME-FACT TEST'
            return result
        with patch.object(build, 'derived_sources', side_effect=changed), \
                patch('tools.brand_sets.navbox.source', side_effect=ValueError('late navbox input')), \
                patch.object(Path, 'write_bytes') as writes:
            with self.assertRaisesRegex(ValueError, 'late navbox input'):
                build.generate(ROOT)
            writes.assert_not_called()

    def test_ordinary_rules_belong_to_the_supplied_root_and_catalog(self):
        minor = {'attributes': [{'id': 'minor_attribute_test', 'zh_name': 'TEST', 'en_name': 'TEST',
                               'category': 'offense', 'unit_type': 'percent'}]}
        ordinary = {'rules': [dict(id='ordinary_minor_test', kind='ordinary', attribute_id='minor_attribute_test',
                                  display_max='1.0', verification='NON-GAME-FACT', native_uid='test')]}
        presets = {'schema_version': 1, 'presets': []}
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as temp:
            root = Path(temp)
            target = root / 'data/equipment/attributes.json'
            target.parent.mkdir(parents=True)
            import json
            target.write_text(json.dumps(ordinary), encoding='utf8')
            loaded = load(root)
        self.assertEqual(ordinary_rows(minor, loaded)[0]['value'], '1.0')
        self.assertEqual(resolve(presets, minor, 'ordinary_minor_test', loaded)['value'], '1.0')
        with self.assertRaisesRegex(ValueError, '未找到普通'):
            resolve(presets, minor, 'ordinary_minor_test')
