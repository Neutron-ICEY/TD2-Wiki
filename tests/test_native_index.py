from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.game_resources import ResourceError, locked, store_at
from tools.asset_import.native_index import build, json_bytes
from tools.asset_import.text_evidence import native_definitions
from tools.asset_import.text_library import TextError, TextLibrary, sha256


UID, GUID = 'B' * 32, 'A' * 32


def native(value='1'):
    return ('Talent Fixture < uid=' + UID + ' >\n{\n myDuration ' + value + '\n'
            ' myUIName "enabled = true, guid = #' + GUID + ', lineVersion = 1, text = \\"Fixture\\""\n}\n').encode()


class NativeIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_ASSET_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = native()
        self.resource = 'hunter/game system data/fixture.mtalent'
        self.menu = 'hunter/localization/packages/english/menus.locpack'
        self.put('evidence/fixture.mtalent', self.old)
        self.definition = dict(file='evidence/fixture.mtalent', sha256=sha256(self.old), bytes=len(self.old),
                               resource_name=self.resource, export_role='manual_raw_text',
                               parser_rule='fruit_definition_scopes@4',
                               parsed=native_definitions(self.old, True, True, True))
        self.sources = dict(schema_version=1, sources=[dict(id='menu', format='menus_csv',
            file='evidence/menus.locpack', sha256='c' * 64, batch_ref=None,
            locale=dict(namespace=self.menu, culture='english', language='en', language_evidence='fixture'))])
        self.register()
        self.resources({self.resource: native('2'), self.menu: ('2,,,\n1,,,\n' + GUID + ',,Updated,\n').encode(),
                        'hunter/unselected.mtalent': native('3')})

    def put(self, file, blob):
        p = self.root / file
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)

    def register(self):
        defs = json_bytes(dict(schema_version=1, parser_rule='fruit_definition_scopes@4',
                               schema_evidence=[], files=[self.definition]))
        refs = json_bytes(dict(schema_version=1, parser_rule='fruit_localization_guid_fields@1',
                              files=[{k: v for k, v in self.definition.items() if k not in ('parsed', 'parser_rule')}],
                              references=[], issues=[]))
        self.put('evidence/native-definitions.json', defs)
        self.put('evidence/native-references.json', refs)
        self.sources['native_definitions'] = dict(file='evidence/native-definitions.json', sha256=sha256(defs))
        self.sources['native_references'] = dict(file='evidence/native-references.json', sha256=sha256(refs), target_sources=['menu'])
        self.put('data/asset-import/text-sources.json', json_bytes(self.sources))

    def resources(self, files):
        rows = []
        for name, blob in sorted(files.items()):
            self.put('resources/game/current/raw_files/' + name, blob)
            rows.append(dict(path='raw_files/' + name, bytes=len(blob), sha256=sha256(blob), source_id='fixture-current'))
        manifest = b''.join(json.dumps(r, separators=(',', ':')).encode() + b'\n' for r in rows)
        self.put('resources/game/manifest.jsonl', manifest)
        self.put('resources/game/source.json', json_bytes(dict(schema_version=1, manifest_sha256=sha256(manifest),
            files=len(rows), bytes=sum(r['bytes'] for r in rows), sources={'fixture-current': dict(
                source_id='fixture-current', origin='SYNTHETIC_TEST', game_build=None, source_container_sha256=None)})))

    def test_reviewed_persistent_index_activation_checks_registration_and_artifacts(self):
        from tools.version_update import activate_index
        candidate='evidence/asset-import/native/acceptance'
        out=self.root/'dist/activation'
        out.mkdir(parents=True)
        before=(self.root/'data/asset-import/text-sources.json').read_bytes()
        build(self.root,candidate)
        spec=self.root/candidate/'native-definitions.json'
        original=spec.read_bytes()
        spec.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            activate_index(self.root,out,candidate)
        self.assertEqual((self.root/'data/asset-import/text-sources.json').read_bytes(),before)
        spec.write_bytes(original)
        active = activate_index(self.root,out,candidate)
        self.assertEqual(active['status'],'activated')
        self.assertEqual((out/'previous-text-sources.json').read_bytes(),before)
        self.assertEqual(activate_index(self.root,out,candidate)['status'],'already_active')

    def test_changed_definitions_and_menus_form_reviewable_candidate_without_registration(self):
        before = (self.root / 'data/asset-import/text-sources.json').read_bytes()
        report = build(self.root, 'dist/review')
        self.assertEqual('REVIEW_CANDIDATE', report['status'])
        self.assertEqual(['raw_files/hunter/unselected.mtalent'], report['unselected_current_raw_files'])
        self.assertEqual({'definition', 'localization'}, {x['role'] for x in report['changes']})
        self.assertFalse(report['registration_updated'])
        self.assertEqual(before, (self.root / 'data/asset-import/text-sources.json').read_bytes())
        library = TextLibrary(self.root, 'dist/review/text-sources-candidate.json')
        result = library.query(key=GUID)
        self.assertEqual([], result['issues'])
        self.assertEqual('Updated', result['results'][0]['text'])
        definitions = library._load_definitions()
        self.assertEqual([], definitions['issues'])
        self.assertEqual('2', definitions['resources'][0]['properties'][0]['raw_value'])

    def test_unchanged_derived_excerpt_is_rebuilt_but_changed_parent_blocks(self):
        fragment = self.old
        parent = self.old + b'\n'
        self.definition['derived_source'] = dict(file='old-parent', sha256=sha256(parent),
            original_resource_name=self.resource, slices=[dict(byte_start=0, byte_end=len(fragment))],
            scope='fixture', currency_uid=UID)
        self.definition['resource_name'] += '#' + UID
        self.register()
        menu = ('2,,,\n1,,,\n' + GUID + ',,Fixture,\n').encode()
        self.resources({self.resource: parent, self.menu: menu})
        report = build(self.root, 'dist/unchanged')
        self.assertEqual('REVIEW_CANDIDATE', report['status'])
        self.assertEqual(fragment, next((self.root / 'dist/unchanged/fragments').iterdir()).read_bytes())
        defs = json.loads((self.root / 'dist/unchanged/native-definitions.json').read_text(encoding='utf-8'))
        self.assertEqual(self.resource + '#' + UID, defs['files'][0]['resource_name'])
        self.assertEqual(UID, defs['files'][0]['derived_source']['currency_uid'])
        self.resources({self.resource: parent + b'\n', self.menu: menu})
        blocked = build(self.root, 'dist/blocked')
        self.assertIn('DERIVED_INPUT_REQUIRES_REVIEW', {r['code'] for r in blocked['issues']})
        self.assertEqual(['report.json'], [p.name for p in (self.root / 'dist/blocked').iterdir()])

    def test_missing_resource_and_stale_manifest_fail_without_partial_index(self):
        current = self.root / 'resources/game/current/raw_files' / self.resource
        current.unlink()
        report = build(self.root, 'dist/missing')
        self.assertEqual('BLOCKED', report['status'])
        self.assertIn('INPUT_MISSING', {r['code'] for r in report['issues']})
        self.put('resources/game/current/raw_files/' + self.resource, b'changed after inventory')
        report = build(self.root, 'dist/stale')
        self.assertIn('INPUT_HASH_MISMATCH', {r['code'] for r in report['issues']})
        self.assertFalse((self.root / 'dist/stale/native-definitions.json').exists())

    def test_parse_errors_block_and_preserve_registration(self):
        self.resources({self.resource: b'Talent Broken < uid=' + UID.encode() + b' >\n{\n',
                        self.menu: b'2,,,\n0,,,\n'})
        report = build(self.root, 'dist/invalid')
        self.assertEqual('BLOCKED', report['status'])
        self.assertTrue(report['issues'])
        self.assertFalse((self.root / 'dist/invalid/text-sources-candidate.json').exists())

    def test_output_and_native_paths_cannot_escape(self):
        with self.assertRaisesRegex(TextError, 'OUTPUT_OUTSIDE_REVIEW_ROOT'):
            build(self.root, '../outside')
        self.definition['resource_name'] = '../outside'
        self.register()
        report = build(self.root, 'dist/path')
        self.assertIn('UNSAFE_PATH', {r['code'] for r in report['issues']})

    def test_existing_output_is_never_overwritten(self):
        build(self.root, 'dist/review')
        with self.assertRaisesRegex(TextError, 'OUTPUT_MUST_BE_FRESH'):
            build(self.root, 'dist/review')

    def test_stable_evidence_candidate_can_be_queried_without_dist(self):
        report = build(self.root, 'evidence/asset-import/native/review')
        self.assertEqual('REVIEW_CANDIDATE', report['status'])
        library = TextLibrary(self.root, 'evidence/asset-import/native/review/text-sources-candidate.json')
        self.assertEqual([], library.query(key=GUID)['issues'])
        self.assertFalse((self.root / 'dist').exists())

    def test_resource_update_lock_prevents_mixed_input_candidate(self):
        with locked(store_at(self.root)):
            with self.assertRaisesRegex(ResourceError, 'RESOURCE_LIBRARY_BUSY'):
                build(self.root, 'dist/busy')
        self.assertFalse((self.root / 'dist/busy').exists())
        self.assertEqual('REVIEW_CANDIDATE', build(self.root, 'dist/unlocked')['status'])

    def test_pending_resource_updates_block_without_output(self):
        for marker, code in [('.transaction', 'PENDING_TRANSACTION_USE_RECOVER'),
                             ('.initializing.json', 'PENDING_INITIALIZATION_USE_RECOVER')]:
            path = self.root / 'resources/game' / marker
            path.write_text('{}', encoding='utf-8')
            with self.assertRaisesRegex(TextError, code):
                build(self.root, 'dist/pending')
            path.unlink()
        self.assertFalse((self.root / 'dist/pending').exists())

    def test_other_export_types_do_not_expand_or_block_selected_native_scope(self):
        manifest_path = self.root / 'resources/game/manifest.jsonl'
        rows = [json.loads(line) for line in manifest_path.read_bytes().splitlines()]
        blob = b'fixture audio export'
        self.put('resources/game/current/audio/hunter/fixture.wem', blob)
        rows.append(dict(path='audio/hunter/fixture.wem', bytes=len(blob), sha256=sha256(blob),
                         source_id='fixture-current'))
        manifest = b''.join(json.dumps(row).encode() + b'\n' for row in sorted(rows, key=lambda row: row['path'].casefold()))
        manifest_path.write_bytes(manifest)
        source_path = self.root / 'resources/game/source.json'
        source = json.loads(source_path.read_bytes())
        source.update(manifest_sha256=sha256(manifest), files=len(rows), bytes=sum(row['bytes'] for row in rows))
        source_path.write_bytes(json_bytes(source))
        report = build(self.root, 'dist/audio')
        self.assertEqual('REVIEW_CANDIDATE', report['status'])
        self.assertEqual(1, report['selected_definition_files'])
        self.assertEqual(1, report['unselected_current_raw_file_count'])


if __name__ == '__main__':
    unittest.main()
