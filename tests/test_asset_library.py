"""Isolated fixtures and real read-only lookups; no exporter or uploader calls."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from fixture_corpus import corpus_root

from tools.asset_import.library import Library, ROOT, main
from tools.asset_import.static_formats import image_metadata, sha256


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_ASSET_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.root.mkdir()
        first = io.BytesIO()
        Image.new('RGBA', (4, 3), (255, 255, 255, 128)).save(first, format='PNG')
        second = io.BytesIO()
        Image.new('RGBA', (4, 3), (20, 30, 40, 255)).save(second, format='PNG')
        self.a, self.b = first.getvalue(), second.getvalue()
        self.put('one/raw/same.png', self.a)
        self.put('one/raw/other.png', self.a)
        self.put('two/raw/same.png', self.b)
        self.put('repeat/raw/same.png', self.a)
        self.write('one/manifest.json', {'assets': [self.row('same-id', 'same.png', self.a),
                                                  self.row('other-id', 'other.png', self.a, container='other-package')]})
        self.write('two/manifest.json', {'assets': [self.row('same-id', 'same.png', self.b)]})
        self.write('repeat/manifest.json', {'assets': [self.row('same-id', 'same.png', self.a)]})
        self.index = {'schema_version': 1, 'batches': [self.batch('one'), self.batch('two'), self.batch('repeat', 'verification')]}
        self.save_index()

    def put(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def write(self, name, data):
        return self.put(name, (json.dumps(data, ensure_ascii=False) + '\n').encode('utf-8'))

    def save_index(self):
        self.write('index.json', self.index)

    def batch(self, name, role='source'):
        return dict(id=name, role=role, format='manifest', file=name + '/manifest.json', base=name)

    def row(self, asset_id, filename, data, container='package'):
        return dict(asset_id=asset_id, raw_path='raw/' + filename, source_entry=filename,
                    source_package=container, source_sha256=sha256(data), category='unknown',
                    width=4, height=3, pixel_hash=image_metadata(data)['pixel_hash'],
                    provenance=dict(source_container=container, source_container_sha256='a' * 64,
                                    resource_name=filename, resource_id='UNKNOWN', game_build='UNKNOWN'))

    def load(self):
        return Library(self.root, 'index.json')

    def cli(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(['--root', str(self.root), '--index', 'index.json', *args])
        return code, json.loads(stdout.getvalue() or stderr.getvalue())

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (sha256(p.read_bytes()), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def test_cross_batch_id_and_same_sha_observations_remain_distinct(self):
        rows = self.load().search(sha256(self.a).upper(), 'sha256')
        self.assertEqual(3, len(rows))
        self.assertEqual(3, len({r['record_key'] for r in rows}))
        self.assertEqual({'one', 'repeat'}, {r['batch_id'] for r in rows})
        self.assertEqual({'same.png', 'other.png'}, {r['source']['entry'] for r in rows})

    def test_active_selection_preserves_original_observation_pointer(self):
        self.index['batches'][0]['observations'] = ['/assets/1']
        self.save_index()
        (self.root / 'one/raw/same.png').unlink()
        library = self.load()
        self.assertEqual([], library.issues)
        rows = library.search(batch_ids=['one'])
        self.assertEqual(['one#/assets/1'], [r['record_key'] for r in rows])
        self.assertEqual(['other-id'], [r['asset_id'] for r in rows])
        self.assertTrue(library.verify(rows)[0]['verification']['passed'])

    def test_active_selection_rejects_unknown_duplicate_or_invalid_pointers(self):
        for selection in (['/assets/99'], ['/assets/0', '/assets/0'], ['/assets/0', 1], '/assets/0'):
            with self.subTest(selection=selection):
                self.index['batches'][0]['observations'] = selection
                self.save_index()
                library = self.load()
                self.assertTrue(any(i['error'] == 'INVALID_OBSERVATION_SELECTION' for i in library.issues))
                self.assertEqual([], library.search(batch_ids=['one']))

    def test_explicit_retired_label_preserves_evidence_without_active_join(self):
        label = dict(name='Recorded label', selector=dict(batch_id='one', asset_id='missing'),
                     evidence=dict(file='old.json', note='original observation'))
        self.index['targets'] = 'targets.json'
        self.save_index()
        self.write('targets.json', dict(application_labels=[label], targets=[]))
        self.assertTrue(any(i['error'] == 'APPLICATION_LABEL_REFERENCE_UNRESOLVED' for i in self.load().issues))
        self.write('targets.json', dict(application_labels=[dict(label, availability='retired')], targets=[]))
        library = self.load()
        self.assertEqual([], library.issues)
        recorded = library.document('targets.json')['application_labels'][0]
        self.assertEqual(label, {k: v for k, v in recorded.items() if k != 'availability'})

    def test_same_filename_different_content_is_not_deduplicated(self):
        rows = self.load().search('same.png', 'path')
        self.assertEqual(3, len(rows))
        self.assertEqual(2, len({r['sha256'] for r in rows}))
        self.assertEqual({'one', 'two', 'repeat'}, {r['batch_id'] for r in rows})

    def test_published_observation_keeps_old_name_but_reads_registered_asset(self):
        self.write('publishing/registry.json',{'entries':[{'id':'wiki-stable','kind':'assets','source':'assets/New.png','title':'File:New.png'}]})
        self.put('assets/New.png',self.a)
        self.write('published.json',{'images':[{'registry_id':'wiki-stable','wiki_filename':'Old.png','source_sha256':sha256(self.a)}]})
        self.index['batches'].append(dict(id='published',role='use',format='publications',file='published.json',base='.'));self.save_index()
        library=self.load();self.assertFalse(library.issues)
        item=library.search(batch_ids=['published'])[0]
        self.assertEqual(item['recorded_path'],'assets/Old.png')
        self.assertEqual(item['wiki_asset_id'],'wiki-stable');self.assertIsNone(item['asset_id'])
        self.assertEqual(item['path'],str(self.root/'assets/New.png'))
        self.assertEqual(item['uses'][0]['wiki_filename'],'Old.png')
        self.assertEqual(item['uses'][0]['current_filename'],'New.png')
        self.assertTrue(library.verify([item])[0]['verification']['passed'])

    def test_publication_without_label_preserves_use_and_evidence(self):
        rows = [dict(registry_id='fixture-labelled', wiki_filename='labelled.png',
                     source_sha256=sha256(self.a), approved_label='已登记名称'),
                dict(registry_id='fixture-unlabelled', wiki_filename='不得猜测名称.png',
                     source_sha256=sha256(self.a))]
        self.write('publications.json', {'images': rows})
        self.index['batches'].append(dict(id='published', role='use', format='publications',
                                         file='publications.json', base='.'))
        self.save_index()
        before = self.snapshot()
        library = self.load()
        self.assertEqual([], library.issues)
        records = library.search(sha256(self.a), 'sha256', batch_ids=['published'])
        self.assertEqual(2, len(records))
        self.assertEqual([['已登记名称'], []], [r['names']['recorded'] for r in records])
        for index, record in enumerate(records):
            self.assertEqual('use', record['record_type'])
            self.assertEqual('published#/images/' + str(index), record['record_key'])
            self.assertEqual(rows[index]['registry_id'], record['uses'][0]['registry_id'])
            self.assertEqual(rows[index]['wiki_filename'], record['uses'][0]['wiki_filename'])
            self.assertEqual([dict(file='publications.json', pointer='/images/' + str(index))],
                             record['evidence'])
            self.assertIsNone(record['source']['resource_id'])
        self.assertEqual([], library.search('不得猜测名称', 'name'))
        self.assertEqual(before, self.snapshot())

    def test_source_groups_require_container_path_hash_and_entry(self):
        library = self.load()
        groups = library.duplicates('source')
        self.assertEqual(1, len(groups))
        # Both one and two have the same recorded container identity even though
        # their exported content differs; preserve this discrepancy in the group.
        self.assertEqual(3, len(groups[0]['members']))
        self.assertEqual(2, len({r['sha256'] for r in groups[0]['members']}))
        self.assertNotIn('other-id', [r['asset_id'] for r in groups[0]['members']])
        self.assertIsNone(library.records[0]['source']['resource_id'])
        self.assertIsNone(library.records[0]['source']['game_build'])

    def test_missing_source_hash_does_not_create_a_source_group(self):
        for name in ('one', 'two', 'repeat'):
            d = json.loads((self.root / name / 'manifest.json').read_text())
            for r in d['assets']:
                r['provenance']['source_container_sha256'] = 'UNKNOWN'
            self.write(name + '/manifest.json', d)
        self.assertEqual([], self.load().duplicates('source'))

    def test_unclassified_is_searchable_without_filename_classification(self):
        rows = self.load().search('unknown', 'category')
        self.assertEqual(4, len(rows))
        self.assertTrue(all(r['category'] is None and r['primary_class'] is None for r in rows))

    def test_annotation_names_are_proposed_and_do_not_promote_mapping(self):
        annotation = dict(self.row('same-id', 'same.png', self.a), proposed_chinese_names=['测试技能'],
                          mapping_status='source_only', technical_category='skill_icon')
        self.write('annotations.json', {'assets': [annotation]})
        self.index['batches'][0]['annotations'] = 'annotations.json'
        self.save_index()
        row = self.load().search('测试技能', 'name')[0]
        self.assertEqual(['测试技能'], row['names']['proposed'])
        self.assertEqual('source_only', row['mapping_status'])
        self.assertEqual([], row['uses'])

    def add_catalog(self, digest):
        self.write('catalog.json', {'brands': [dict(entity_key='fixture:entity', zh_name='已登记业务名',
                                                   wiki_filename='frozen.png', asset_mapping=dict(
                                                       selected_asset_id='same-id', selected_source_sha256=digest,
                                                       asset_role='fixture_role'))]})
        self.index['catalogs'] = [dict(file='catalog.json', batch_id='one')]
        self.save_index()

    def test_catalog_use_joins_selected_id_and_hash_not_other_equal_bytes(self):
        self.add_catalog(sha256(self.a))
        library = self.load()
        rows = library.search('已登记业务名', 'name')
        self.assertEqual(1, len(rows))
        self.assertEqual('same-id', rows[0]['asset_id'])
        self.assertEqual('one', rows[0]['batch_id'])
        other = next(r for r in library.records if r['asset_id'] == 'other-id')
        self.assertEqual([], other['uses'])

    def test_conflicting_catalog_hash_does_not_attach_business_identity(self):
        self.add_catalog(sha256(self.b))
        library = self.load()
        self.assertTrue(library.issues)
        self.assertEqual([], library.search('已登记业务名', 'name'))

    def test_default_search_does_not_read_or_stat_resource_files(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('resource read forbidden')), \
                patch.object(Path, 'is_file', side_effect=AssertionError('resource stat forbidden')):
            rows = self.load().search('same.png', 'path')
        self.assertEqual(3, len(rows))
        self.assertTrue(all(r['file_state'] == 'not_checked' for r in rows))

    def test_conflicting_annotation_is_reported_as_partial_coverage(self):
        self.write('annotations.json', {'assets': [self.row('same-id', 'same.png', self.b)]})
        self.index['batches'][0]['annotations'] = 'annotations.json'
        self.save_index()
        code, output = self.cli('search', 'same.png')
        self.assertEqual(2, code)
        self.assertEqual('partial', output['coverage'])
        self.assertIn('ANNOTATION_CONTENT_CONFLICT', output['issues'][0]['error'])

    def add_sprites(self):
        self.put('atlas.png', self.a)
        self.put('sprite.definition', b'NON-GAME-FACT DEFINITION')
        ref = dict(path='sprite.definition', sha256=sha256(b'NON-GAME-FACT DEFINITION'))
        self.write('sprites.json', [dict(png=dict(path='atlas.png', sha256=sha256(self.a)),
                                        definition=ref, decompiled=ref, texture='fixture.dds', width=4, height=3,
                                        sprites=[dict(name=n, uv=dict(x=0, y=0, w=1, h=1), rect=[0, 0, 4, 3], line=4)
                                                 for n in ('box', 'bag')])])
        self.index['batches'].append(dict(id='sprites', role='definition', format='material_sprites', file='sprites.json'))
        self.save_index()

    def test_sprite_resolves_original_atlas_rect_and_definition(self):
        self.add_sprites()
        library = self.load()
        row = library.search('box', 'sprite')[0]
        self.assertEqual(str(self.root / 'atlas.png'), row['path'])
        self.assertEqual([0, 0, 4, 3], row['sprite']['rect'])
        self.assertEqual('xywh', row['sprite']['rect_convention'])
        self.assertEqual('atlas_file_not_region_hash', row['sprite']['content_scope'])
        self.assertTrue(library.verify([row])[0]['verification']['passed'])

    def test_sprite_observations_do_not_inflate_physical_duplicate_groups(self):
        before = self.load().duplicates('bytes')
        self.add_sprites()
        after = self.load().duplicates('bytes')
        self.assertEqual([len(g['members']) for g in before], [len(g['members']) for g in after])

    def test_derived_parent_digest_is_not_mistaken_for_output_digest(self):
        self.put('child.png', self.b)
        self.write('derived.json', [dict(raw_path='child.png', source_sha256=sha256(self.a),
                                         size=[4, 3], native_crop_sha256=sha256(self.b),
                                         provenance=dict(crop_box=[0, 0, 4, 3])),
                                   dict(raw_path='no-output.png', source_sha256=sha256(self.a))])
        self.index['batches'].append(dict(id='derived', role='derived', format='derived', file='derived.json'))
        self.save_index()
        r = self.load().search('child.png')[0]
        self.assertEqual(sha256(self.b), r['sha256'])
        self.assertEqual(sha256(self.a), r['derivation']['parent_sha256'])
        self.assertEqual('xyxy', r['derivation']['rect_convention'])
        self.assertEqual((4, 3), (r['width'], r['height']))
        unknown = self.load().search('no-output.png')[0]
        self.assertIsNone(unknown['sha256'])
        self.assertIsNone(unknown['derivation']['rect_convention'])

    def test_shared_relations_do_not_merge_or_assign_entities(self):
        self.write('shared.json', {'groups': [dict(type='pixel_duplicate', legitimate_shared_icon=True,
                                                  digest='fixture-pixels', members=['same-id', 'other-id'],
                                                  confirmed_application_entities=[['talent', 'A'], ['talent', 'B']])]})
        self.index['shared_relations'] = dict(file='shared.json', batch_id='one')
        self.save_index()
        library = self.load()
        group = library.duplicates('shared')[0]
        self.assertEqual(2, len(group['members']))
        self.assertTrue(all(r['uses'] == [] for r in library.records))
        self.assertEqual(4, len(library.records))

    def test_query_and_verify_write_nothing_and_do_not_modify_history(self):
        before = self.snapshot()
        with patch.object(Path, 'write_text', side_effect=AssertionError('write forbidden')), \
                patch.object(Path, 'write_bytes', side_effect=AssertionError('write forbidden')):
            code, result = self.cli('search', 'same.png', '--verify')
            self.assertEqual(0, code)
            self.assertEqual(3, result['total'])
            self.assertTrue(all(r['verification']['passed'] for r in result['results']))
            self.cli('duplicates', '--kind', 'bytes', '--verify')
        self.assertEqual(before, self.snapshot())

    def test_missing_or_changed_files_fail_verification(self):
        (self.root / 'one/raw/same.png').write_bytes(b'changed')
        (self.root / 'two/raw/same.png').unlink()
        code, output = self.cli('search', 'same.png', '--verify')
        self.assertEqual(3, code)
        self.assertEqual({'match', 'mismatch', 'missing'},
                         {r['verification']['checks'][0]['state'] for r in output['results']})

    def test_outside_root_is_reported_and_never_read(self):
        self.write('one/manifest.json', {'assets': [dict(self.row('outside', 'same.png', self.a), raw_path='../../outside.png')]})
        code, output = self.cli('search', 'outside', '--verify')
        self.assertEqual(3, code)
        self.assertEqual('outside_root', output['results'][0]['file_state'])
        self.assertIsNone(output['results'][0]['path'])

    def test_explicit_historical_root_rebases_without_rewriting_evidence(self):
        previous = 'D:/recorded-project/TD2-wiki'
        recorded = previous + '/one/raw/same.png'
        self.write('one/manifest.json', {'assets': [dict(self.row('relocated', 'same.png', self.a), raw_path=recorded)]})
        self.index['historical_roots'] = [previous]
        self.save_index()
        before = self.snapshot()
        library = self.load()
        row = library.search('relocated', 'id')[0]
        self.assertEqual(recorded, row['recorded_path'])
        self.assertEqual(str(self.root / 'one/raw/same.png'), row['path'])
        row['references'] = [dict(path=recorded, sha256=sha256(self.a))]
        self.assertTrue(library.verify([row])[0]['verification']['passed'])
        self.assertEqual(before, self.snapshot())

    def test_historical_root_mapping_rejects_other_roots_and_traversal(self):
        previous = 'D:/recorded-project/TD2-wiki'
        self.index['historical_roots'] = [previous]
        self.save_index()
        for recorded in (previous + '-other/one/raw/same.png', previous + '/../outside.png',
                         'D:/unregistered/one/raw/same.png'):
            with self.subTest(recorded=recorded):
                self.write('one/manifest.json', {'assets': [dict(self.row('outside', 'same.png', self.a), raw_path=recorded)]})
                code, output = self.cli('search', 'outside', '--verify')
                self.assertEqual(3, code)
                self.assertEqual('outside_root', output['results'][0]['file_state'])
                self.assertIsNone(output['results'][0]['path'])

    def test_historical_roots_require_explicit_absolute_paths(self):
        for value in ('D:/recorded-project/TD2-wiki', ['../old-root'], [None]):
            with self.subTest(value=value):
                self.index['historical_roots'] = value
                self.save_index()
                with self.assertRaisesRegex(ValueError, 'INVALID_HISTORICAL_ROOTS'):
                    self.load()

    def test_unknown_hash_is_not_a_successful_verification(self):
        row = self.row('unknown-hash', 'same.png', self.a)
        row['source_sha256'] = 'UNKNOWN'
        self.write('one/manifest.json', {'assets': [row]})
        code, output = self.cli('search', 'unknown-hash', '--verify')
        self.assertEqual(3, code)
        self.assertEqual('unknown', output['results'][0]['verification']['checks'][0]['state'])

    def test_missing_batch_is_not_reported_as_resource_absence(self):
        self.index['batches'].append(dict(id='unavailable', role='source', format='manifest', file='missing.json'))
        self.save_index()
        code, output = self.cli('search', 'not-present')
        self.assertEqual(2, code)
        self.assertEqual(0, output['total'])
        self.assertEqual('partial', output['coverage'])
        self.assertEqual('unavailable', output['issues'][0]['batch_id'])

    def test_cli_pagination_batch_and_invalid_inputs(self):
        code, output = self.cli('search', 'same.png', '--limit', '1', '--offset', '1')
        self.assertEqual(0, code)
        self.assertEqual(3, output['total'])
        self.assertEqual(1, len(output['results']))
        self.assertEqual(1, self.cli('search', '', '--batch', 'two')[1]['total'])
        self.assertEqual(2, self.cli('search', '', '--batch', 'typo')[0])
        self.assertEqual(2, self.cli('search', '', '--limit', '0')[0])
        self.assertEqual(2, self.cli('search', '', '--offset', '-1')[0])

    def test_duplicate_batch_ids_are_rejected(self):
        self.index['batches'].append(self.index['batches'][0])
        self.save_index()
        self.assertEqual(2, self.cli('batches')[0])

    def test_incremental_export_receipts_keep_sources_and_reloading_is_idempotent(self):
        old = self.load().records
        for name, container_hash in [('new-version', 'b' * 64), ('other-source', 'c' * 64)]:
            self.put(name + '/raw/original.png', self.a)
            self.write(name + '/export-manifest.json', {'exports': [dict(
                exported_path=name + '/raw/original.png', exported_file_sha256=sha256(self.a),
                decoded_image_sha256=image_metadata(self.a)['pixel_hash'], width=4, height=3,
                source_container='NON-GAME-FACT/' + name, source_container_sha256=container_hash,
                resource_name='hunter/ui/fixture-target', resource_id='UNKNOWN', game_build='UNKNOWN',
                mapping_status='EXTRACTED_UNMAPPED')]})
            self.index['batches'].append(dict(id=name, role='source', format='exports',
                                            file=name + '/export-manifest.json'))
        self.save_index()
        before = self.snapshot()
        first, second = self.load(), self.load()
        self.assertEqual(old, first.records[:len(old)])
        self.assertEqual(first.records, second.records)
        self.assertEqual(6, len(first.records))
        rows = first.search('hunter/ui/fixture-target', 'path')
        self.assertEqual(2, len(rows))
        self.assertEqual(2, len({r['record_key'] for r in rows}))
        self.assertEqual(2, len({r['source']['container_sha256'] for r in rows}))
        self.assertEqual({sha256(self.a)}, {r['sha256'] for r in rows})
        self.assertTrue(all(r['source']['resource_id'] is None and not r['uses'] for r in rows))
        self.assertTrue(all(r['verification']['passed'] for r in first.verify(rows)))
        self.assertTrue(set(r['record_key'] for r in rows) <=
                        set(r['record_key'] for r in first.search('unknown', 'category')))
        self.assertEqual(before, self.snapshot())


class ExistingCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = corpus_root()
        cls.library = Library(root=cls.root)

    def test_registered_batches_are_readable(self):
        self.assertEqual([], self.library.issues)
        # The historical cohort must survive incremental registration; its size
        # is not a permanent upper bound on the library.
        historical = {'app-v29-main', 'app-v29-repeat', 'game-brand-20261013',
                      'brand-regions-20261013', 'brand-sprites-20261013', 'material-sprites-20261016',
                      'material-candidates-20261016', 'weave-icons-20261016', 'wiki-use-20261016',
                      'export-logo02-single', 'export-logo01-single', 'export-logo-validation',
                      'export-logo-acceptance', 'export-logo-dev', 'material-export-20261016'}
        self.assertTrue(historical <= {b['id'] for b in self.library.index['batches']})

    def test_targeted_ui_exports_are_queryable_verified_and_unmapped(self):
        batches = {'ui-inventory-20261016', 'ui-menu12-20261016',
                   'ui-menu34-20261016', 'ui-loadout-20261016'}
        self.assertLessEqual(batches, {b['id'] for b in self.library.index['batches']})
        rows = self.library.search(batch_ids=batches)
        self.assertEqual(7, len(rows))
        self.assertEqual(7, len({r['sha256'] for r in rows}))
        self.assertEqual(7, len({r['record_key'] for r in rows}))
        self.assertTrue(all(r['mapping_status'] == 'EXTRACTED_UNMAPPED' for r in rows))
        self.assertTrue(all(r['source']['entry'].startswith('hunter/baked/ui/spritesheets/') for r in rows))
        self.assertTrue(all(r['source']['game_build'] is None and not r['uses'] for r in rows))
        self.assertTrue(all(r['verification']['passed'] for r in self.library.verify(rows)))

    def test_real_cross_batch_same_sha_retains_multiple_sources(self):
        rows = self.library.search('250d4693fe5ec526b9b19e8c7e23c4a4c765f64b9501f12ee093c355436b122b', 'sha256')
        self.assertTrue({'app-v29-main', 'app-v29-repeat', 'wiki-use-20261016'} <= {r['batch_id'] for r in rows})
        self.assertGreaterEqual(len(rows), 7)
        self.assertEqual(len(rows), len({r['record_key'] for r in rows}))
        self.assertGreater(len({r['source']['entry'] for r in rows}), 1)

    def test_real_same_name_with_different_bytes_and_unclassified_lookup(self):
        self.assertGreater(len({r['sha256'] for r in self.library.search('gear2.png', 'path')}), 1)
        unknown = self.library.search('unknown', 'category')
        self.assertTrue(any('technician.scale-100.png' in (r['path'] or '') for r in unknown))

    def test_known_skill_and_all_six_specializations(self):
        skill = self.library.search('蜂窝-恢复', 'name')
        self.assertTrue(any(r['path'].endswith('skill0.png') for r in skill))
        for label in ('烈焰之墙', '技师', '重机枪手', '生存专家', '爆破专家', '精准射手'):
            with self.subTest(label=label):
                rows = self.library.search(label, 'name')
                self.assertTrue(rows)
                self.assertTrue(all(r['source']['resource_id'] is None for r in rows))

    def test_specialization_labels_match_independent_cached_constructor_evidence(self):
        notes = self.library.document(self.library.index['targets'])
        for label in notes['application_labels']:
            with self.subTest(label=label['name']):
                proof = label['evidence']
                metadata = self.library.document(proof['file'])
                types = {t['name']: t for t in metadata['types']}
                ctor = next(m for m in types['Division2BuildTool.Model.Specialization']['methods'] if m['name'] == '.ctor')
                self.assertEqual(proof['constructor_token'], ctor['token'])
                cctor = next(m for m in types['Division2BuildTool.Model.AppData']['methods'] if m['token'] == proof['method_token'])
                il = cctor['il']
                pos = next(i for i, instruction in enumerate(il) if instruction['offset'] == proof['literal_offset'])
                row = next(r for r in self.library.records if Library._selected(r, label['selector']))
                self.assertEqual('ldstr', il[pos]['opcode'])
                self.assertEqual(row['source']['entry'].replace('.scale-100', ''), il[pos]['operand'])
                self.assertEqual(label['name'], il[pos - 1]['operand'])
                by_offset = {instruction['offset']: instruction for instruction in ctor['il']}
                self.assertEqual('ldarg.2', by_offset[21]['opcode'])
                self.assertEqual('ldarg.3', by_offset[33]['opcode'])
                self.assertTrue(by_offset[34]['operand']['name'].endswith('::<Image>k__BackingField'))

    def test_ui_candidates_resolve_to_existing_sources_and_definitions(self):
        for name, rect in [('category_no_brand', [256, 512, 128, 128]),
                           ('menu_prototype_cache', [512, 512, 128, 128])]:
            with self.subTest(sprite=name):
                row = self.library.search(name, 'sprite')[0]
                self.assertEqual(rect, row['sprite']['rect'])
                self.assertTrue(Path(row['path']).is_file())
                self.assertTrue(self.library.verify([row])[0]['verification']['passed'])
        self.assertTrue(self.library.search('背包与齿轮组合', 'name'))

    def test_live_lookup_and_verification_preserve_source_records(self):
        paths = [self.root / p for p in ('dist/asset-import/asset-manifest.json',
                                    'data/brand-sets/brands.json', 'publishing/image-publications.json')]
        before = {str(p): sha256(p.read_bytes()) for p in paths}
        rows = self.library.search('gear2.scale-100.png', 'path')
        self.assertTrue(all(r['verification']['passed'] for r in self.library.verify(rows)))
        self.assertEqual(before, {str(p): sha256(p.read_bytes()) for p in paths})


if __name__ == '__main__':
    unittest.main()
