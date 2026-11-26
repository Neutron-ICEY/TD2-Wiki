from tools import identity as identity_catalog
"""Brand identity, remote preflight and staging gates; never contact the site."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from fixture_corpus import corpus_path

from tools.asset_import.brand_publication import publication_status
from tools.asset_import.contract import compatible_brand_filename, detect_contract, subset
from tools.asset_import.pipeline import stage_plan
from tools.asset_import.resource_references import effective_image_reference
from tools.brand_sets.brands import load_catalog, validate_catalog
from tools.publish.bundle import load_state, title_key

ROOT = Path(__file__).resolve().parents[1]


class BrandPublicationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = copy.deepcopy(load_catalog(ROOT))
        self.item = self.catalog['brands'][0]
        self.ui = identity_catalog.read_json(ROOT / 'data/brand-sets/equipment-ui.json')

    def assert_file_revision_lineage(self, baseline, receipt):
        self.assertEqual(baseline['file_revision'], receipt['upload_timestamp'])
        if baseline['revision_id'] == receipt['revision']:
            return
        cleanup = json.loads((ROOT / 'publishing/history/file-notes-cleanup-20261017-002.json').read_bytes())
        readback = json.loads(corpus_path('dist/file-notes-cleanup-20261017-002/readback.json').read_bytes())
        self.assertEqual(cleanup['status'], 'COMPLETE')
        self.assertEqual(cleanup['verification']['issues'], [])
        matches = [r for r in cleanup['saved'] if r['filename'] == receipt['wiki_filename']]
        self.assertEqual(len(matches), 1)
        saved = matches[0]
        self.assertEqual(saved['result'], 'Success')
        self.assertEqual(saved['pageid'], receipt['file_page_id'])
        self.assertEqual(saved['before_revision'], receipt['revision'])
        self.assertEqual(saved['baserevid'], receipt['revision'])
        self.assertEqual(saved['revision_id'], baseline['revision_id'])
        pages = [p for p in readback['pages'] if p['title'] == baseline['title']]
        self.assertEqual(len(pages), 1)
        page = pages[0]
        self.assertEqual(page['pageid'], receipt['file_page_id'])
        self.assertEqual(page['ns'], 6)
        self.assertEqual(page['revisions'][0]['parentid'], receipt['revision'])
        self.assertEqual(page['revisions'][0]['revid'], baseline['revision_id'])
        self.assertEqual(page['revisions'][0]['slots']['main']['content'], '')
        self.assertEqual(page['imageinfo'][0]['timestamp'], receipt['upload_timestamp'])

    def test_page_identity_stays_separate_from_verified_file_publication(self):
        published = load_state(ROOT / 'publishing/baseline.json', 'huijiwiki-td2', root=ROOT)
        for item in self.catalog['brands']:
            asset = identity_catalog.asset(item['asset_ref'])
            filename = asset['title'].split(':', 1)[1]
            self.assertIsNone(item['game_internal_id'])
            self.assertEqual(item['published_icon']['confirmed_on_wiki'], title_key(asset['title'], 6) in published)
            self.assertTrue(item['published_icon']['local_available'])
            self.assertEqual(filename, item['wiki_filename'])
            self.assertEqual(identity_catalog.page(item['entity_ref'])['kind'], 'pages')
            self.assertEqual(hashlib.sha256((ROOT / asset['source']).read_bytes()).hexdigest(), asset['content_sha256'])

    def test_unrecorded_file_revision_or_changed_upload_is_rejected(self):
        receipt = json.loads((ROOT / 'publishing/history/brand-naming-final-20261014-001-brand01-move-receipt.json').read_bytes())
        readback = json.loads(corpus_path('dist/file-notes-cleanup-20261017-002/readback.json').read_bytes())
        page = next(p for p in readback['pages'] if p['title']=='文件:'+receipt['wiki_filename'])
        baseline = {'title': page['title'], 'revision_id': page['revisions'][0]['revid'],
                    'file_revision': page['imageinfo'][0]['timestamp']}
        self.assert_file_revision_lineage(baseline, receipt)
        for field, value in [('revision_id', 999999999), ('file_revision', 'unrecorded-upload')]:
            with self.subTest(field=field):
                with self.assertRaises(AssertionError):
                    self.assert_file_revision_lineage({**baseline, field: value}, receipt)

    def test_no_new_chinese_primary_key_or_duplicate_brand_id(self):
        keys = [b['entity_key'] for b in self.catalog['brands']]
        self.assertEqual(len(keys), 26)
        self.assertEqual(len(set(keys)), 26)
        for key in keys:
            self.assertRegex(key, '^brand_source:[0-9a-f]{20}$')

    def test_source_name_approval_and_mapping_are_required_independently(self):
        for field, value in [('entity_verified', False), ('catalog_ready', False), ('zh_name', '虚构名称')]:
            bad = copy.deepcopy(self.catalog); bad['brands'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_catalog(bad, self.ui)
        bad = copy.deepcopy(self.catalog); bad['brands'][0]['name_policy']['business_name_approved'] = False
        with self.assertRaises(ValueError): validate_catalog(bad, self.ui)
        bad = copy.deepcopy(self.catalog); bad['brands'][0]['asset_mapping']['mapping_verified'] = False
        with self.assertRaises(ValueError): validate_catalog(bad, self.ui)

    def test_reject_duplicate_keys_and_false_page_identity(self):
        bad = copy.deepcopy(self.catalog); bad['brands'].append(copy.deepcopy(bad['brands'][0]))
        with self.assertRaises(ValueError): validate_catalog(bad, self.ui)
        bad = copy.deepcopy(self.catalog); bad['brands'][0]['entity_ref'] = ''
        with self.assertRaises(ValueError): validate_catalog(bad, self.ui)

    def test_existing_brand_helper_consumes_all_approved_filenames(self):
        wiki=subset(ROOT)(ROOT)
        for item in self.catalog['brands']:
            self.assertTrue(compatible_brand_filename(ROOT, item['entity_key'], item['wiki_filename']))
            self.assertIn('[[File:'+item['wiki_filename']+'|', wiki.template('TD2品牌图片', {'品牌': item['entity_ref']}))
        self.assertFalse(compatible_brand_filename(ROOT, 'brand_source:' + '0' * 20, self.item['wiki_filename']))
        self.assertFalse(compatible_brand_filename(ROOT, self.item['entity_key'], 'wrong.png'))

    def test_preflight_separates_all_required_states(self):
        ready = dict(ns=6, title='文件:' + self.item['wiki_filename'], missing=True, imagerepository='', protection=[])
        rights = {'read', 'edit', 'createpage', 'upload'}
        self.assertEqual(publication_status(self.item, ready, rights, True), 'READY_TO_UPLOAD')
        unknowns = [None, {}, dict(ready, protection=[{'type': 'upload', 'level': 'sysop'}]), dict(ready, imagerepository='shared')]
        for page in unknowns: self.assertEqual(publication_status(self.item, page, rights, True), 'REMOTE_UNKNOWN')
        self.assertEqual(publication_status(self.item, ready, rights - {'upload'}, True), 'REMOTE_UNKNOWN')
        self.assertEqual(publication_status(self.item, ready, rights, False), 'REMOTE_UNKNOWN')
        present = dict(pageid=1, protection=[], imageinfo=[{'sha1': self.item['asset_mapping']['selected_source_sha1']}])
        self.assertEqual(publication_status(self.item, present, rights, True), 'ALREADY_PRESENT')
        present['imageinfo'][0]['sha1'] = '0' * 40
        self.assertEqual(publication_status(self.item, present, rights, True), 'FILE_CONFLICT')
        bad = copy.deepcopy(self.item); bad['catalog_ready'] = False
        self.assertEqual(publication_status(bad, ready, rights, True), 'ENTITY_NOT_READY')
        bad = copy.deepcopy(self.item); bad['asset_mapping']['mapping_verified'] = False
        self.assertEqual(publication_status(bad, ready, rights, True), 'MAPPING_NOT_VERIFIED')

    def test_reference_overrides_are_exact_and_do_not_promote_mapping(self):
        binding = dict(source_filename='talent.png.png', source_platform='apk', internal_key='NON-GAME-FACT')
        fingerprint = hashlib.sha256(json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        data = dict(overrides=[dict(binding_sha256=fingerprint, original_filename='talent.png.png', source_platform='apk',
            corrected_logical_filename='talent.png', override_id='fixture', target_asset_ids=['NON-GAME-FACT'])])
        result = effective_image_reference(binding, data)
        self.assertTrue(result['corrected']); self.assertFalse(result['mapping_verified'])
        self.assertEqual(result['source_filename'], 'talent.png')
        unrelated = dict(binding, internal_key='OTHER')
        self.assertFalse(effective_image_reference(unrelated, data)['corrected'])
        self.assertEqual(effective_image_reference(dict(binding, source_filename='correct.png'), data)['source_filename'], 'correct.png')

    def test_stage_blocks_unknown_remote_state_and_alternative_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / 'data/brand-sets', root / 'data/brand-sets')
            shutil.copytree(ROOT / 'wiki/templates', root / 'wiki/templates')
            (root / 'tests').mkdir(); shutil.copy2(ROOT / 'tests/wiki_subset.py', root / 'tests/wiki_subset.py')
            (root / 'publishing').mkdir(exist_ok=True); shutil.copy2(ROOT / 'publishing/registry.json', root / 'publishing/registry.json')
            item = copy.deepcopy(self.item); item['asset_mapping']['selected_raw_path'] = 'raw/brand.png'
            # This fixture represents a new, preflighted upload regardless of the
            # selected real brand's current publication lifecycle.
            item['publication_status'] = 'READY_TO_UPLOAD'; item['publication_ready'] = True
            item['publication_authorized'] = False
            item['published_icon'] = {'wiki_file': '', 'confirmed_on_wiki': False}
            item.pop('publication_receipt', None)
            (root / 'data/brand-sets/brands.json').write_text(json.dumps(dict(schema_version=1, brands=[item]), ensure_ascii=False), encoding='utf-8')
            blob = (ROOT / 'assets' / item['wiki_filename']).read_bytes()
            (root / 'raw').mkdir(); (root / 'raw/brand.png').write_bytes(blob)
            out = root / 'review'; (out / 'normalized').mkdir(parents=True); (out / 'normalized' / item['wiki_filename']).write_bytes(blob)
            asset = dict(status='approved', confidence='exact', stable_id=item['entity_key'], icon_key='TD2品牌图片|品牌='+item['entity_ref'],
                resolver_contract='brand_image', publication_status='READY_TO_UPLOAD', asset_id=item['asset_mapping']['selected_asset_id'],
                normalized_filename=item['wiki_filename'], intended_wiki_filename=item['wiki_filename'], raw_path='raw/brand.png',
                source_sha256=item['asset_mapping']['selected_source_sha256'], normalized_sha256=item['asset_mapping']['selected_source_sha256'],
                pixel_hash=item['asset_mapping']['decoded_pixel_hash'], evidence=['proof'], game_entities=[item['zh_name']], category='brand')
            proof = dict(evidence_id='proof', confidence='exact', candidate_stable_id=asset['stable_id'], candidate_icon_key=asset['icon_key'],
                source_asset_id=asset['asset_id'], source_path=asset['raw_path'], candidate_game_entity=item['zh_name'])
            (out / 'mapping-evidence.json').write_text(json.dumps({'mappings': [proof]}), encoding='utf-8')
            contract = detect_contract(ROOT)
            self.assertEqual(len(stage_plan(root, out, [asset], contract, source_root=root)[0]), 1)
            for change in ({'publication_status': 'REMOTE_UNKNOWN'}, {'source_sha256': item['asset_mapping']['source_sha256'][0] if item['asset_mapping']['source_sha256'][0] != asset['source_sha256'] else '0' * 64}, {'raw_path': 'raw/other.png'}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'BRAND_PUBLICATION_GATE'):
                    stage_plan(root, out, [dict(asset, **change)], contract, source_root=root)
            item['publication_status'] = 'ALREADY_PRESENT'
            (root / 'data/brand-sets/brands.json').write_text(json.dumps(dict(schema_version=1, brands=[item]), ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'BRAND_PUBLICATION_GATE'):
                stage_plan(root, out, [asset], contract, source_root=root)


if __name__ == '__main__':
    unittest.main()
