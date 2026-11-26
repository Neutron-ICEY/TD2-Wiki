from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import game_resources as resources
from tools.game_resources import selection
from tools.game_resources.layers import header_identity
from tools.asset_import.text_evidence import native_definitions
from tools.equipment.native import Native


EXCLUDED = ['materials', 'raw_files/hunter/shaderbytecode', 'raw_files/hunter/shadercache']
MAP = 'raw_files/hunter/maps/' + '1' * 32
LAYER = MAP + '/settings/' + '2' * 32
CHILD = 'hunter/game system data/juice/talent/Child.mtalent'


def descriptor(kind='navmesh', uid='2' * 32):
    return ('{ content = {}, header = { type = "' + kind + '", uid = #' + uid + ', }, }').encode()


class Interrupted(BaseException):
    pass


class ResourceSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_GAME_RESOURCES_TEST_TMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = self.root / 'resources/game'
        self.current = self.store / 'current'
        self.source = self.root / 'incoming/export'
        self.plan = self.root / 'dist/plan'
        self.events = io.StringIO()
        redirect = redirect_stderr(self.events)
        redirect.__enter__()
        self.addCleanup(redirect.__exit__, None, None, None)
        self.old = dict(source_id='old', origin='fixture', game_build=None, source_container_sha256=None)
        self.new = {**self.old, 'source_id': 'new'}
        self.put(self.current, 'raw_files/hunter/game/item', b'old')
        self.put(self.current, 'materials/hunter/atlas.png', b'keep old material')
        resources.initialize(self.root, self.old)
        self.put(self.source, 'raw_files/hunter/game/item', b'new')
        for name in EXCLUDED:
            self.put(self.source, name + '/nested/unused', b'excluded payload')
        self.json(selection.PROFILE_FILE, dict(schema_version=1, id='wiki', excluded_directories=EXCLUDED))
        self.json('data/asset-import/locations.json', dict(schema_version=1, locations={}))
        self.json('data/equipment/native-map.json', dict(schema_version=1, entities=[]))
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[]))
        self.native_files = {'files': [{'path': 'hunter/game/item', 'includes': ['hunter/game/schema']}]}
        self.native_index()

    def put(self, base, name, content):
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def json(self, name, value):
        return self.put(self.root, name, resources.encoded(value))

    def native_index(self, sources=None):
        definition = self.json('evidence/definitions.json', self.native_files)
        reference = self.json('evidence/references.json', {'files': []})
        self.json('data/asset-import/text-sources.json', {
            'schema_version': 1, 'sources': sources or [],
            'native_definitions': {'file': 'evidence/definitions.json', 'sha256': resources.digest(definition)},
            'native_references': {'file': 'evidence/references.json', 'sha256': resources.digest(reference)}})

    def include_fixture(self, include, parent):
        self.json(selection.PROFILE_FILE, resources.read_json(resources.ROOT / selection.PROFILE_FILE))
        blob = ('include "' + include + '"\nTalent Child < uid=' + 'A' * 32 + ' > : Parent\n{\n}\n').encode()
        self.put(self.source, 'raw_files/' + CHILD, blob)
        self.put(self.source, 'raw_files/' + parent,
                 ('Talent Parent < uid=' + 'B' * 32 + ' >\n{\n myValue 8\n}\n').encode())
        parsed = native_definitions(blob, include_data=True, include_objects=True)
        self.assertFalse(parsed['issues'])
        self.native_files = {'files': [{'resource_name': CHILD, 'file': 'evidence/saved-fragment.mtalent',
                                       'parsed': parsed}]}
        self.native_index()
        native = Native(self.source / 'raw_files')
        self.assertEqual([row['internal_name'] for row in native.lineage(native.record(CHILD, 'A' * 32))],
                         ['Child', 'Parent'])

    def test_relative_include_blocks_plan_before_scan(self):
        self.include_fixture('../../../baked/art/Parent.mtalent', 'hunter/baked/art/Parent.mtalent')
        before = self.current_bytes()
        with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
            with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED.*baked/art/Parent'):
                self.prepare()
        self.assertEqual(before, self.current_bytes())
        self.assertFalse(self.plan.exists())

    def test_relative_include_blocks_apply_of_plan_that_omitted_it(self):
        self.include_fixture('../../../baked/art/Parent.mtalent', 'hunter/baked/art/Parent.mtalent')
        # Reproduce the previous guard's dependency set: only the owning file,
        # already registered, and no relative parent. Metadata and rules stay frozen.
        with patch.object(selection, 'native_include_path', side_effect=lambda owner, value: owner):
            self.prepare()
        before = self.current_bytes()
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED.*baked/art/Parent'):
            resources.apply_plan(self.root, self.plan)
        self.assertEqual(before, self.current_bytes())
        self.assertFalse((self.store / '.transaction').exists())

    def test_include_spellings_match_native_lineage_and_dependency_identity(self):
        parent = 'hunter/game system data/juice/talent/Parent.mtalent'
        expected = None
        for include in ('Parent.mtalent', './Parent.mtalent', '../talent/Parent.mtalent',
                        'sub/../Parent.mtalent', '.\\Parent.mtalent', parent):
            with self.subTest(include=include):
                self.include_fixture(include, parent)
                result = self.guard()['required_paths_sha256']
                if expected is None:
                    expected = result
                self.assertEqual(result, expected)
        self.assertEqual(selection.native_include_path('raw_files/' + CHILD,
                         'hunter/game system data/juice/talent/sub/../Parent.mtalent'), 'raw_files/' + parent)

    def test_selected_relative_parent_import_and_repeat_remain_stable(self):
        parent = 'hunter/game system data/juice/talent/Parent.mtalent'
        self.include_fixture('./Parent.mtalent', parent)
        result = self.prepare()
        resources.apply_plan(self.root, self.plan)
        self.assertEqual(result['changes']['added'], 2)
        self.assertEqual(result['wiki_review'], dict(equipment=1, talents=2))
        self.assertTrue((self.current / 'raw_files' / parent).is_file())
        native = Native(self.current / 'raw_files')
        self.assertEqual([r['internal_name'] for r in native.lineage(native.record(CHILD, 'A' * 32))],
                         ['Child', 'Parent'])
        before = self.current_bytes()
        self.plan = self.root / 'dist/repeat'
        repeated = self.prepare()
        self.assertEqual(repeated['changes'], dict(added=0, modified=0, deleted=0, unchanged=3,
                                                  retained=1, copy_bytes=0))
        self.assertEqual(repeated['wiki_review'], {})
        resources.apply_plan(self.root, self.plan)
        self.assertEqual(before, self.current_bytes())
        resources.status(self.root, True)

    def test_include_outside_raw_root_and_host_absolute_paths_rejected(self):
        for include, message in (
                ('../../../../../outside.mtalent', 'NATIVE_INCLUDE_OUTSIDE_RAW_ROOT'),
                ('hunter/../../outside.mtalent', 'NATIVE_INCLUDE_OUTSIDE_RAW_ROOT'),
                ('/outside.mtalent', 'ABSOLUTE_NATIVE_INCLUDE'),
                ('C:/outside.mtalent', 'ABSOLUTE_NATIVE_INCLUDE'),
                ('C:outside.mtalent', 'ABSOLUTE_NATIVE_INCLUDE'),
                ('\\\\server\\share\\outside.mtalent', 'ABSOLUTE_NATIVE_INCLUDE')):
            with self.subTest(include=include):
                self.native_files = {'files': [{'resource_name': CHILD,
                    'parsed': {'includes': [{'path': include}]}}]}
                self.native_index()
                with self.assertRaisesRegex(resources.ResourceError, message):
                    self.prepare()
                self.assertFalse(self.plan.exists())

    def test_cross_namespace_include_stays_inside_raw_root(self):
        self.include_fixture('../../../../rogue/future/Parent.mtalent', 'rogue/future/Parent.mtalent')
        self.assertEqual(selection.native_include_path('raw_files/' + CHILD,
                         '../../../../rogue/future/Parent.mtalent'), 'raw_files/rogue/future/Parent.mtalent')
        self.prepare()
        resources.apply_plan(self.root, self.plan)
        self.assertTrue((self.current / 'raw_files/rogue/future/Parent.mtalent').is_file())

    def test_relative_include_requires_original_owner_and_uses_registered_alias(self):
        self.include_fixture('../../../baked/art/Parent.mtalent', 'hunter/baked/art/Parent.mtalent')
        row = self.native_files['files'][0]
        row.pop('resource_name')
        self.native_index()
        with self.assertRaisesRegex(resources.ResourceError, 'NATIVE_INCLUDE_OWNER_MISSING'):
            self.guard()
        row['file'] = 'dist/archive/Child.mtalent'
        self.json('data/asset-import/locations.json', dict(schema_version=1, locations={row['file']: {
            'path': 'resources/game/current/raw_files/' + CHILD, 'sha256': 'a' * 64}}))
        self.native_index()
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED.*baked/art/Parent'):
            self.guard()

    def test_transitive_relative_includes_use_each_defining_file(self):
        self.include_fixture('./Parent.mtalent', 'hunter/game system data/juice/talent/Parent.mtalent')
        self.native_files['files'].append({'resource_name': 'hunter/game system data/juice/talent/Parent.mtalent',
            'parsed': {'includes': [{'path': '../../../baked/art/Grandparent.mtalent'}]}})
        self.native_index()
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED.*baked/art/Grandparent'):
            self.guard()

    def prepare(self, **kwargs):
        return resources.make_plan(self.root, self.source, self.new, self.plan, profile='wiki', **kwargs)

    def guard(self):
        return selection.dependencies(self.root, selection.load_selection(self.root, 'wiki'))

    def current_bytes(self):
        return {name: path.read_bytes() for name, path, _ in resources.files_in(self.current)}

    def test_profile_contains_only_approved_directories(self):
        rules = selection.load_selection(resources.ROOT, 'wiki')
        layers = rules['layer_types']
        self.assertEqual(len(layers), 16)
        self.assertEqual(list(layers.values()).count('navmesh'), 8)
        self.assertEqual(list(layers.values()).count('globalillumination'), 8)
        self.assertEqual(set(rules['excluded_directories']) - set(layers), set(EXCLUDED + [
            'raw_files/hunter/baked/art', 'images/hunter/maps', 'images/hunter/baked_maps']))

    def layer_profile(self):
        rules = dict(schema_version=2, id='wiki', excluded_directories=EXCLUDED + [LAYER],
                     layer_types={LAYER: 'navmesh'})
        self.json(selection.PROFILE_FILE, rules)
        return rules

    def test_layer_pruning_preserves_new_discovery_unknowns_and_repeat(self):
        rules = selection.load_selection(resources.ROOT, 'wiki')
        self.json(selection.PROFILE_FILE, {k: rules[k] for k in ('schema_version', 'excluded_directories', 'layer_types')}
                  | {'id': 'wiki'})
        excluded = rules['excluded_directories']
        for name in excluded:
            self.put(self.source, name + '/nested/unread', b'excluded')
        for name, kind in rules['layer_types'].items():
            self.put(self.source, name + '/layerdata.mlayer', descriptor(kind, Path(name).name))
        preserved = [
            'raw_files/' + ns + '/game system data/' + part + '/future-uid.definition'
            for ns in ('hunter', 'rogue') for part in
            ('juice/item', 'juice/gearbrand', 'juice/talent', 'crafting', 'rewards', 'loot', 'vendors')]
        preserved += [MAP + '/entities/mission.mscript', MAP + '/settings/new-uid/layerdata.mlayer',
                      LAYER + '_new/unknown', 'raw_files/hunter/baked_maps/known/layers/terrain',
                      'raw_files/hunter/baked_maps/new/reward.mbucket', 'images/hunter/baked/art/future.png',
                      'images/rogue/maps/future.png', 'raw_files/hunter/localization/new/text',
                      'raw_files/snowdrop/modules/core/schema', 'future_unknown/definition']
        for name in preserved:
            self.put(self.source, name, b'future input')
        original_scan, original_open = os.scandir, Path.open
        def excluded_path(path):
            p = Path(path)
            if p.is_relative_to(self.source):
                name = p.relative_to(self.source).as_posix()
                return any(name == e or name.startswith(e + '/') for e in excluded)
            return False
        def scan(path):
            self.assertFalse(excluded_path(path), 'descended into excluded directory')
            return original_scan(path)
        opened_descriptors = set()
        def opened(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if 'r' in mode and excluded_path(path):
                relative = path.relative_to(self.source).as_posix()
                self.assertIn(relative, {p + '/layerdata.mlayer' for p in rules['layer_types']})
                opened_descriptors.add(relative)
            return original_open(path, *args, **kwargs)
        with patch.object(resources.os, 'scandir', side_effect=scan), patch.object(Path, 'open', new=opened):
            report = self.prepare()
            result = resources.apply_plan(self.root, self.plan)
            self.plan = self.root / 'dist/repeat'
            repeated = self.prepare()
            before = self.current_bytes()
            again = resources.apply_plan(self.root, self.plan)
        self.assertEqual(len(opened_descriptors), 16)
        self.assertEqual(report['files'], len(preserved) + 1)
        self.assertEqual(report['skipped_directories'], sorted(excluded, key=str.casefold))
        self.assertEqual(result['layer_evidence'], again['layer_evidence'])
        self.assertEqual(repeated['changes'], dict(added=0, modified=0, deleted=0,
                         unchanged=len(preserved) + 1, retained=1, copy_bytes=0))
        self.assertEqual(before, self.current_bytes())
        self.assertEqual(resources.read_json(self.store / 'source.json')['source_counts']['old'], 1)
        self.assertEqual(report['timings']['stages']['layer_validation']['calls'], 1)
        resources.status(self.root, True)

    def test_invalid_layer_rules_and_discovery_exclusions_rejected(self):
        for name in ('raw_files', 'raw_files/hunter/game system data',
                     'raw_files/rogue/game system data/juice/item',
                     'raw_files/hunter/game system data/rewards'):
            with self.subTest(name=name):
                self.json(selection.PROFILE_FILE, dict(schema_version=1, id='wiki', excluded_directories=[name]))
                with self.assertRaisesRegex(resources.ResourceError, 'DISCOVERY_SCOPE_EXCLUDED'):
                    selection.load_selection(self.root, 'wiki')
        for mapping, message in (({}, 'MAP_EXCLUSION_REQUIRES_LAYER_TYPE'),
                                 ({LAYER: 'mission'}, 'INVALID_LAYER_TYPES'),
                                 ({MAP + '/entities': 'navmesh'}, 'INVALID_LAYER_TYPES')):
            with self.subTest(mapping=mapping):
                rules = self.layer_profile()
                rules['layer_types'] = mapping
                self.json(selection.PROFILE_FILE, rules)
                with self.assertRaisesRegex(resources.ResourceError, message):
                    selection.load_selection(self.root, 'wiki')

    def test_layer_invalid_type_uid_or_missing_header_rejected_before_scan(self):
        self.layer_profile()
        for blob, message in ((descriptor('mission'), 'LAYER_TYPE_MISMATCH'),
                              (descriptor(uid='3' * 32), 'LAYER_UID_MISMATCH'),
                              (b'{ content = {} }', 'INCOMPLETE_LAYER_HEADER')):
            with self.subTest(message=message):
                self.put(self.source, LAYER + '/layerdata.mlayer', blob)
                with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
                    with self.assertRaisesRegex(resources.ResourceError, message):
                        self.prepare()
                self.assertFalse(self.plan.exists())

    def test_missing_descriptor_and_layer_file_rejected(self):
        self.layer_profile()
        path = self.put(self.source, LAYER, b'file, not layer')
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_PATH_KIND_CHANGED'):
            self.prepare()
        path.unlink()
        path.mkdir()
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_DESCRIPTOR_MISSING'):
            self.prepare()

    def test_layer_descriptor_and_presence_are_frozen(self):
        self.layer_profile()
        self.prepare()  # The known directory may be absent in a partial export.
        self.assertIsNone(resources.read_json(self.plan / 'plan.json')['layer_evidence'][LAYER])
        path = self.put(self.source, LAYER + '/layerdata.mlayer', descriptor())
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_CHANGED'):
            resources.apply_plan(self.root, self.plan)
        self.plan = self.root / 'dist/present'
        self.prepare()
        path.write_bytes(descriptor() + b'\n')
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_CHANGED'):
            resources.apply_plan(self.root, self.plan)
        path.unlink()
        path.parent.rmdir()
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_CHANGED'):
            resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.store / '.transaction').exists())

    def test_missing_layer_evidence_cannot_bypass_apply_guard(self):
        self.layer_profile()
        self.prepare()
        plan = resources.read_json(self.plan / 'plan.json')
        plan.pop('layer_evidence')
        (self.plan / 'plan.json').write_bytes(resources.encoded(plan))
        (self.plan / 'plan.sha256').write_text(resources.digest(self.plan / 'plan.json'))
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_REQUIRED'):
            resources.apply_plan(self.root, self.plan)

    def test_layer_changed_during_plan_rejected(self):
        self.layer_profile()
        path = self.put(self.source, LAYER + '/layerdata.mlayer', descriptor())
        original = resources.inventory
        def inventory(*args, **kwargs):
            result = original(*args, **kwargs)
            path.write_bytes(descriptor() + b'\n')
            return result
        with patch.object(resources, 'inventory', side_effect=inventory):
            with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_CHANGED'):
                self.prepare()
        self.assertFalse((self.plan / 'plan.json').exists())

    def test_layer_changed_during_install_blocks_commit_and_can_retry(self):
        self.layer_profile()
        path = self.put(self.source, LAYER + '/layerdata.mlayer', descriptor())
        self.prepare()
        original = resources.os.replace
        def replace(source, target):
            result = original(source, target)
            if Path(source) == self.store / '.transaction/payload':
                path.write_bytes(descriptor() + b'\n')
            return result
        with patch.object(resources.os, 'replace', side_effect=replace):
            with self.assertRaisesRegex(resources.ResourceError, 'LAYER_EVIDENCE_CHANGED'):
                resources.apply_plan(self.root, self.plan)
        self.assertTrue((self.store / '.transaction').exists())
        path.write_bytes(descriptor())
        resources.recover(self.root)
        resources.status(self.root, True)

    def test_layer_plan_retry_requires_frozen_descriptor(self):
        self.layer_profile()
        path = self.put(self.source, LAYER + '/layerdata.mlayer', descriptor())
        self.prepare()
        original = resources.os.replace
        def replace(source, target):
            if Path(source) == self.store / '.transaction/payload':
                raise Interrupted()
            return original(source, target)
        with patch.object(resources.os, 'replace', side_effect=replace):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        path.write_bytes(descriptor('mission'))
        with self.assertRaisesRegex(resources.ResourceError, 'LAYER_TYPE_MISMATCH'):
            resources.recover(self.root)
        path.write_bytes(descriptor())
        self.assertEqual(resources.recover(self.root)['previous_state'], 'applying')
        resources.status(self.root, True)

    def test_image_container_identity_is_not_a_raw_path_but_actual_input_is_protected(self):
        image = 'hunter/baked/art/brand.png'
        self.json(selection.PROFILE_FILE, dict(schema_version=1, id='wiki',
                  excluded_directories=EXCLUDED + ['raw_files/hunter/baked/art']))
        self.json('evidence/images.json', {'assets': [dict(asset_id='logo',
                  raw_path='resources/game/current/images/' + image, source_sha256='a' * 64,
                  source_entry=image, provenance={'resource_name': image})]})
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[dict(
                  id='fixture', role='evidence', format='manifest', file='evidence/images.json')]))
        self.guard()
        self.native_files['files'][0]['includes'] = [image]
        self.native_index()
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()
        self.native_files['files'][0]['includes'] = []
        self.native_index()
        self.json(selection.PROFILE_FILE, dict(schema_version=1, id='wiki',
                  excluded_directories=EXCLUDED + ['images/hunter/baked/art']))
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_image_sprite_and_parent_native_references_remain_protected(self):
        self.json(selection.PROFILE_FILE, dict(schema_version=1, id='wiki',
                  excluded_directories=EXCLUDED + ['raw_files/hunter/baked/art']))
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[dict(
                  id='fixture', role='evidence', format='derived', file='evidence/images.json')]))
        self.json('evidence/images.json', [dict(derived_file='assets/logo.png',
                  provenance={'internal_asset_name': 'hunter/baked/art/identity'})])
        self.guard()
        self.json('evidence/images.json', [dict(derived_file='assets/logo.png', sprite='hunter/baked/art/identity')])
        self.guard()
        for key in ('original_atlas', 'sprite_definition'):
            with self.subTest(key=key):
                self.json('evidence/images.json', [dict(derived_file='assets/logo.png',
                          provenance={'internal_asset_name': 'hunter/baked/art/identity'},
                          **{key: {'path': 'hunter/baked/art/required.sprite'}})])
                with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
                    self.guard()
        self.json('evidence/images.json', [dict(derived_file='assets/logo.png',
                  references=[{'resource_name': 'hunter/baked/art/required.sprite'}])])
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_required_dependency_in_known_layer_blocks_pruning(self):
        self.layer_profile()
        self.put(self.source, LAYER + '/layerdata.mlayer', descriptor())
        self.native_files['files'][0]['includes'] = [LAYER.removeprefix('raw_files/') + '/new.schema']
        self.native_index()
        with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
            with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
                self.prepare()

    def test_layer_directory_link_rejected_before_descriptor_read(self):
        self.layer_profile()
        outside = self.root / 'outside'
        self.put(outside, 'layerdata.mlayer', descriptor())
        target = self.source / LAYER
        target.parent.mkdir(parents=True)
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(target))
        else:
            target.symlink_to(outside, target_is_directory=True)
        self.addCleanup(lambda: target.rmdir() if os.name == 'nt' else target.unlink())
        with self.assertRaisesRegex(resources.ResourceError, 'LINK_NOT_ALLOWED'):
            self.prepare()

    def test_layer_header_handles_strings_comments_and_rejects_ambiguous_identity(self):
        blob = (b'{ content = { string = "} header = {", /* } */ nested = { type = "mission" } }, // }\n'
                + descriptor()[len(b'{ content = {}, '):])
        self.assertEqual(header_identity(blob), dict(type='navmesh', uid='2' * 32))
        for blob in (b'{ content = ' + descriptor() + b' }',
                     descriptor()[:-1] + b'header = { type = "navmesh" } }',
                     descriptor().replace(b'type =', b'type = "mission", type ='),
                     descriptor()[:-1], b'{ header = { type = "unterminated } }'):
            with self.subTest(blob=blob):
                with self.assertRaises((resources.ResourceError, ValueError)):
                    header_identity(blob)

    def test_pruning_before_descent_and_hash_unknowns_retained_and_repeat_stable(self):
        unknown = ['raw_files/hunter/maps/graph', 'raw_files/hunter/game/currencies/craft',
                   'raw_files/hunter/shadercache_new/file', 'images/hunter/art/brand.png',
                   'new_kind/future/file', 'raw_files/rogue/shadercache/file']
        for name in unknown:
            self.put(self.source, name, name.encode())
        original_scan, original_open = os.scandir, Path.open
        def forbidden(path):
            p = Path(path)
            if p.is_relative_to(self.source):
                name = p.relative_to(self.source).as_posix().casefold()
                return any(name == x or name.startswith(x + '/') for x in EXCLUDED)
            return False
        def scan(path):
            self.assertFalse(forbidden(path), 'entered excluded subtree')
            return original_scan(path)
        def opened(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if 'r' in mode:
                self.assertFalse(forbidden(path), 'opened excluded payload')
            return original_open(path, *args, **kwargs)
        with patch.object(resources.os, 'scandir', side_effect=scan), patch.object(Path, 'open', new=opened):
            report = self.prepare()
            self.put(self.source, 'materials/nested/new-file', b'changed outside selection')
            result = resources.apply_plan(self.root, self.plan)
            self.plan = self.root / 'dist/repeat'
            repeated = self.prepare()
        self.assertEqual(report['files'], 1 + len(unknown))
        self.assertEqual(report['skipped_directories'], EXCLUDED)
        self.assertEqual(report['changes']['deleted'], 0)
        self.assertEqual(repeated['changes'], dict(added=0, modified=0, deleted=0,
                                                  unchanged=1 + len(unknown), retained=1, copy_bytes=0))
        self.assertEqual((self.current / 'materials/hunter/atlas.png').read_bytes(), b'keep old material')
        self.assertEqual(resources.read_json(self.store / 'source.json')['source_counts']['old'], 1)
        metadata = resources.read_json(self.store / 'source.json')['sources']['new']
        self.assertEqual(metadata['import_scope']['mode'], 'partial')
        self.assertEqual(metadata['import_scope']['selection'], result['selection'])
        self.assertNotIn('import_scope', self.new)
        self.assertEqual(report['timings']['stages']['resource_hash']['files'], report['files'])
        self.assertEqual(result['timings']['stages']['copy_hash']['bytes'], report['changes']['copy_bytes'])
        self.assertNotIn('source_verify', result['timings']['stages'])
        self.assertNotIn('timings', resources.read_json(self.plan / 'plan.json'))

    def test_directory_match_is_case_insensitive_exact_and_directory_only(self):
        (self.source / 'materials').rename(self.source / 'MATERIALS')
        self.put(self.source, 'raw_files/hunter/shadercache2/file', b'keep')
        result = self.prepare()
        self.assertEqual(result['files'], 2)
        other = self.root / 'flat'
        self.put(other, 'materials', b'file, not directory')
        result = resources.inventory(other, self.root / 'flat.jsonl', 'new', EXCLUDED)
        self.assertEqual(result['files'], 1)

    def test_complete_scope_rejected_before_any_scan(self):
        with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
            with self.assertRaisesRegex(resources.ResourceError, 'FILTERED_COMPLETE_SCOPE'):
                self.prepare(complete_scopes=['raw_files'])
        self.assertFalse(self.plan.exists())

    def test_apply_rejects_complete_scope_even_with_deletion_flag(self):
        self.prepare()
        plan = resources.read_json(self.plan / 'plan.json')
        plan['complete_scopes'] = ['raw_files']
        (self.plan / 'plan.json').write_bytes(resources.encoded(plan))
        (self.plan / 'plan.sha256').write_text(resources.digest(self.plan / 'plan.json'))
        with self.assertRaisesRegex(resources.ResourceError, 'FILTERED_COMPLETE_SCOPE'):
            resources.apply_plan(self.root, self.plan, True)
        self.assertFalse((self.store / '.transaction').exists())

    def test_rules_changed_after_plan_rejected(self):
        self.prepare()
        path = self.root / selection.PROFILE_FILE
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(resources.ResourceError, 'SELECTION_RULES_CHANGED'):
            resources.apply_plan(self.root, self.plan)

    def test_rules_changed_during_plan_never_produce_applicable_plan(self):
        original = resources.inventory
        def inventory(*args, **kwargs):
            result = original(*args, **kwargs)
            path = self.root / selection.PROFILE_FILE
            path.write_bytes(path.read_bytes() + b'\n')
            return result
        with patch.object(resources, 'inventory', side_effect=inventory):
            with self.assertRaisesRegex(resources.ResourceError, 'SELECTION_RULES_CHANGED'):
                self.prepare()
        self.assertFalse((self.plan / 'plan.json').exists())

    def test_dependency_metadata_changed_after_plan_rejected(self):
        self.prepare()
        self.json('data/equipment/native-map.json', {'schema_version': 1, 'entities': [
            {'path': 'hunter/shadercache/required'}]})
        with self.assertRaisesRegex(resources.ResourceError, 'DEPENDENCY_INPUT_CHANGED'):
            resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.store / '.transaction').exists())

    def test_native_mapping_and_transitive_include_conflicts_rejected(self):
        self.json('data/equipment/native-map.json', {'schema_version': 1, 'entities': [
            {'path': 'hunter/shadercache/required:4'}]})
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.prepare()
        self.json('data/equipment/native-map.json', {'schema_version': 1, 'entities': []})
        self.native_files['files'][0]['includes'] = ['hunter/shaderbytecode/parent#uid']
        self.native_index()
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.prepare()
        self.assertFalse(self.plan.exists())

    def test_text_alias_conflict_rejected(self):
        self.json('data/asset-import/locations.json', {'schema_version': 1, 'locations': {
            'dist/old/text': {'path': 'resources/game/current/materials/hunter/text', 'sha256': 'a' * 64}}})
        self.native_index([{'file': 'dist/old/text'}])
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_required_path_matching_is_case_insensitive(self):
        self.native_index([{'file': 'Resources/Game/Current/Materials/Hunter/required.png'}])
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_import_scope_conflict_and_source_id_reuse_do_not_rewrite_provenance(self):
        self.new['import_scope'] = {'mode': 'complete'}
        with self.assertRaisesRegex(resources.ResourceError, 'SOURCE_IMPORT_SCOPE_CONFLICT'):
            self.prepare()
        self.new.pop('import_scope')
        self.prepare()
        resources.apply_plan(self.root, self.plan)
        path = self.root / selection.PROFILE_FILE
        path.write_bytes(path.read_bytes() + b'\n')
        self.plan = self.root / 'dist/reused-source'
        with self.assertRaisesRegex(resources.ResourceError, 'SOURCE_ID_METADATA_CONFLICT'):
            self.prepare()

    def test_selected_image_parent_conflict_but_unselected_observation_ignored(self):
        self.json('evidence/images.json', {'rows': [
            {'derived_file': 'assets/ok.png', 'original_atlas': {'path': 'images/hunter/art/ok.png'}},
            {'derived_file': 'assets/problem.png', 'original_atlas': {
                'path': 'resources/game/current/materials/hunter/needed.png'}}]})
        batch = dict(id='fixture', role='evidence', format='derived', collection='rows',
                     file='evidence/images.json', observations=['/rows/0'])
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[batch]))
        self.guard()
        batch['observations'] = ['/rows/1']
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[batch]))
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_historical_image_parent_alias_respects_registered_batch_base(self):
        self.json('data/asset-import/locations.json', {'schema_version': 1, 'locations': {
            'dist/images/hunter/raw/materials/parent.png': {
                'path': 'resources/game/current/materials/needed.png', 'sha256': 'a' * 64}}})
        self.json('evidence/images.json', [{'derived_file': 'assets/ok.png',
                                          'original_atlas': {'path': 'hunter/raw/materials/parent.png'}}])
        batch = dict(id='fixture', role='evidence', format='derived', base='dist/images', file='evidence/images.json')
        self.json('data/asset-import/batches.json', dict(schema_version=1, batches=[batch]))
        with self.assertRaisesRegex(resources.ResourceError, 'REQUIRED_RESOURCE_EXCLUDED'):
            self.guard()

    def test_excluded_root_link_still_rejected_without_descending(self):
        original = self.source / 'materials'
        outside = self.root / 'outside'
        original.rename(outside)
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(outside), str(original))
        else:
            original.symlink_to(outside, target_is_directory=True)
        self.addCleanup(lambda: original.rmdir() if os.name == 'nt' else original.unlink())
        with self.assertRaisesRegex(resources.ResourceError, 'LINK_NOT_ALLOWED'):
            self.prepare()

    def test_missing_or_changed_dependency_index_fails_closed(self):
        path = self.root / 'evidence/definitions.json'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(resources.ResourceError, 'DEPENDENCY_INDEX_HASH_MISMATCH'):
            self.guard()
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.guard()

    def test_selected_file_drift_still_rejected(self):
        self.prepare()
        self.put(self.source, 'raw_files/hunter/game/item', b'bad')
        with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_CONTENT_DRIFT'):
            resources.apply_plan(self.root, self.plan)
        self.assertTrue((self.store / '.transaction').exists())

    def test_new_unknown_file_waits_for_next_plan(self):
        self.prepare()
        self.put(self.source, 'z_new_kind/new', b'new')
        resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.current / 'z_new_kind/new').exists())

    def test_rules_changed_during_copy_blocks_commit(self):
        self.prepare()
        original = resources.copy_verified
        def copy(source, target, expected):
            result = original(source, target, expected)
            if Path(target) == self.store / '.transaction/payload':
                path = self.root / selection.PROFILE_FILE
                path.write_bytes(path.read_bytes() + b'\n')
            return result
        with patch.object(resources, 'copy_verified', side_effect=copy):
            with self.assertRaisesRegex(resources.ResourceError, 'SELECTION_RULES_CHANGED'):
                resources.apply_plan(self.root, self.plan)
        self.assertTrue((self.store / '.transaction').exists())
        self.assertFalse((self.store / 'updates').exists())
        self.assertFalse(json.loads(self.events.getvalue().splitlines()[-1])['succeeded'])

    def test_filtered_interruption_and_recovery_preserve_old_excluded_files(self):
        self.prepare()
        original = resources.os.replace
        def replace(source, target):
            if Path(source) == self.store / '.transaction/payload':
                raise Interrupted()
            return original(source, target)
        with patch.object(resources.os, 'replace', side_effect=replace):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual(resources.recover(self.root)['previous_state'], 'applying')
        self.assertEqual((self.current / 'materials/hunter/atlas.png').read_bytes(), b'keep old material')
        self.assertEqual((self.current / 'raw_files/hunter/game/item').read_bytes(), b'new')
        resources.status(self.root, True)

    def test_unfiltered_mode_keeps_original_full_inventory_and_old_plan_format(self):
        resources.make_plan(self.root, self.source, self.new, self.plan)
        plan = resources.read_json(self.plan / 'plan.json')
        self.assertNotIn('selection', plan)
        self.assertNotIn('dependencies', plan)
        (self.root / selection.PROFILE_FILE).unlink()
        result = resources.apply_plan(self.root, self.plan)
        self.assertEqual(result['files'], 4)
        for name in EXCLUDED:
            self.assertTrue((self.current / name / 'nested/unused').is_file())

    def test_cli_profile_and_machine_readable_timings(self):
        metadata = self.json('source.json', self.new)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(resources.main(['plan', '--root', str(self.root), '--source', str(self.source),
                             '--metadata', str(metadata), '--output', str(self.plan), '--profile', 'wiki']), 0)
        result = json.loads(output.getvalue())
        event = json.loads(self.events.getvalue().splitlines()[-1])
        self.assertEqual(event['command'], 'plan')
        self.assertEqual(event['event'], 'resource_timing')
        self.assertTrue(event['succeeded'])
        self.assertEqual(result['timings']['stages'], event['stages'])

    def cli_plan(self, *options):
        metadata = self.json('cli-source.json', self.new)
        output = io.StringIO()
        with redirect_stdout(output):
            code = resources.main(['plan', '--root', str(self.root), '--source', str(self.source),
                                   '--metadata', str(metadata), '--output', str(self.plan), *options])
        return code, json.loads(output.getvalue()) if output.getvalue() else None

    def test_cli_defaults_to_wiki_and_apply_uses_frozen_scope(self):
        self.json(selection.PROFILE_FILE, resources.read_json(resources.ROOT / selection.PROFILE_FILE))
        code, result = self.cli_plan()
        self.assertEqual(code, 0)
        self.assertEqual(result['files'], 1)
        plan = resources.read_json(self.plan / 'plan.json')
        self.assertEqual(plan['selection']['profile'], 'wiki')
        self.assertEqual(len(plan['selection']['excluded_directories']), 22)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(resources.main(['apply', '--root', str(self.root), '--plan', str(self.plan)]), 0)
        self.assertEqual((self.current / 'raw_files/hunter/game/item').read_bytes(), b'new')
        self.assertEqual((self.current / 'materials/hunter/atlas.png').read_bytes(), b'keep old material')
        for name in EXCLUDED:
            self.assertFalse((self.current / name / 'nested/unused').exists())

    def test_cli_unfiltered_keeps_full_source_without_profile_registration(self):
        (self.root / selection.PROFILE_FILE).unlink()
        code, result = self.cli_plan('--unfiltered')
        self.assertEqual(code, 0)
        self.assertEqual(result['files'], 4)
        self.assertNotIn('selection', resources.read_json(self.plan / 'plan.json'))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(resources.main(['apply', '--root', str(self.root), '--plan', str(self.plan)]), 0)
        for name in EXCLUDED:
            self.assertTrue((self.current / name / 'nested/unused').is_file())

    def test_cli_complete_scope_requires_unfiltered_and_retains_deletion_gate(self):
        (self.source / 'raw_files/hunter/game/item').unlink()
        with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
            code, _ = self.cli_plan('--complete-scope', 'raw_files')
        self.assertEqual(code, 2)
        self.assertIn('FILTERED_COMPLETE_SCOPE_NOT_ALLOWED', self.events.getvalue())
        self.assertFalse(self.plan.exists())
        code, result = self.cli_plan('--unfiltered', '--complete-scope', 'raw_files')
        self.assertEqual(code, 0)
        self.assertEqual(result['changes']['deleted'], 1)
        args = ['apply', '--root', str(self.root), '--plan', str(self.plan)]
        before = self.current_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(resources.main(args), 2)
            self.assertEqual(before, self.current_bytes())
            self.assertEqual(resources.main([*args, '--allow-deletions']), 0)
        self.assertFalse((self.current / 'raw_files/hunter/game/item').exists())

    def test_cli_rejects_mixed_scope_flags_in_either_order(self):
        for options in (['--profile', 'wiki', '--unfiltered'], ['--unfiltered', '--profile', 'wiki']):
            with self.subTest(options=options), patch.object(resources, 'make_plan', side_effect=AssertionError('must not plan')):
                with self.assertRaises(SystemExit) as error:
                    self.cli_plan(*options)
                self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.plan.exists())

    def test_cli_missing_default_profile_fails_without_unfiltered_fallback(self):
        (self.root / selection.PROFILE_FILE).unlink()
        with patch.object(resources, 'inventory', side_effect=AssertionError('must not scan')):
            code, _ = self.cli_plan()
        self.assertEqual(code, 2)
        self.assertFalse(self.plan.exists())


if __name__ == '__main__':
    unittest.main()
