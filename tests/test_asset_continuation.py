"""Non-game fixtures for new Main-core role and remote-file gates."""
import copy
import unittest

from tools.asset_import.continuation import classify, file_decision, preflight_entry, verified_core_bindings, verified_uploads


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.ui = {'major_names': {'red': 'NON-GAME-FACT core'}}
        self.core = dict(scope='gear_main', status='exact_existing', confidence='exact',
            source_scope_membership='GearAttribute1List', wiki_stable_id='red',
            wiki_chinese_name='NON-GAME-FACT core', source_chinese_name='NON-GAME-FACT core',
            source_internal_name='fixture-core', source_internal_keys=['fixture::Main'])
        self.bindings = [dict(source_platform=p, category='attribute', internal_key='fixture-core',
            source_filename='fixture.png', confidence='exact', evidence=[dict(source_field='fixture::Main')])
            for p in ('apk', 'windows')]

    def test_exact_main_scope_and_independent_platform_binding(self):
        self.assertEqual(set(verified_core_bindings('red', self.core, self.bindings, self.ui)), {'apk', 'windows'})

    def test_matching_name_in_wrong_domain_cannot_approve(self):
        for changed in ({'scope': 'gear_secondary'}, {'status': 'source_only'}, {'source_scope_membership': 'BrandBonuses'}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verified_core_bindings('red', dict(self.core, **changed), self.bindings, self.ui)
        wrong = copy.deepcopy(self.bindings); wrong[0]['evidence'][0]['source_field'] = 'fixture::Bonus'
        with self.assertRaises(ValueError):
            verified_core_bindings('red', self.core, wrong, self.ui)

    def test_platform_conflict_and_ambiguous_binding_fail_closed(self):
        wrong = copy.deepcopy(self.bindings); wrong[0]['source_filename'] = 'different.png'
        with self.assertRaises(ValueError):
            verified_core_bindings('red', self.core, wrong, self.ui)
        with self.assertRaises(ValueError):
            verified_core_bindings('red', self.core, self.bindings + [self.bindings[0]], self.ui)

    def test_technical_classification_does_not_upgrade_identity(self):
        asset = {'evidence': ['fixture']}
        proof = {'candidate_category': 'talent', 'confidence': 'exact'}
        self.assertEqual(classify(asset, {'fixture': proof}), ('talent_icon', 'source_only'))
        self.assertEqual(classify(asset, {'fixture': dict(proof, confidence='medium')}), ('unknown', 'candidate'))
        self.assertEqual(classify({'evidence': []}, {}), ('unknown', 'unresolved'))

    def test_unknown_remote_state_or_existing_target_cannot_overwrite(self):
        remote = {'file_preflight': {'rights': ['read', 'edit', 'createpage', 'upload'],
            'pages': [{'title': 'File:fixture.png', 'missing': True, 'protection': []}]}}
        self.assertTrue(preflight_entry(remote, 'fixture.png')['missing'])
        for changed in ({'missing': False}, {'protection': [{'type': 'upload', 'level': 'sysop'}]}):
            blocked = copy.deepcopy(remote); blocked['file_preflight']['pages'][0].update(changed)
            with self.assertRaises(ValueError):
                preflight_entry(blocked, 'fixture.png')
        with self.assertRaises(ValueError):
            preflight_entry(remote, 'unknown.png')

    def test_existing_same_hash_is_skipped_different_hash_is_conflict(self):
        expected = 'a' * 40
        page = {'pageid': 1, 'imageinfo': [{'sha1': expected}]}
        self.assertEqual(file_decision(page, expected), 'already_present')
        self.assertEqual(file_decision(page, 'b' * 40), 'FILE_CONFLICT')
        self.assertEqual(file_decision({'pageid': 1}, expected), 'REMOTE_UNVERIFIED')
        self.assertEqual(file_decision({'missing': True}, expected), 'REMOTE_UNVERIFIED')

    def test_upload_success_requires_actual_bytes_metadata_and_one_version(self):
        entry = dict(wiki_filename='fixture.png', source_sha1='a' * 40,
            normalized_sha256='b' * 64, byte_size=100, width=7, height=5)
        info = dict(sha1='a' * 40, size=100, width=7, height=5, mime='image/png',
            timestamp='2026-10-13T00:00:00Z', descriptionurl='https://example.invalid/fixture')
        page = dict(title='File:fixture.png', pageid=1, lastrevid=2, imageinfo=[info])
        observed = {'query': {'pages': [page]}}
        downloaded = {'fixture.png': {'sha256': 'b' * 64, 'sha1': 'a' * 40, 'size': 100}}
        result = verified_uploads({'entries': [entry]}, observed, downloaded)
        self.assertEqual(result[0]['upload_status'], 'uploaded_verified')
        for changed in ({'sha1': 'c' * 40}, {'width': 8}, {'mime': 'image/svg+xml'}, {'size': 101}):
            broken = copy.deepcopy(observed); broken['query']['pages'][0]['imageinfo'][0].update(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                verified_uploads({'entries': [entry]}, broken, downloaded)
        broken = copy.deepcopy(observed); broken['query']['pages'][0]['imageinfo'].append(info)
        with self.assertRaises(ValueError):
            verified_uploads({'entries': [entry]}, broken, downloaded)
        corrupted = copy.deepcopy(downloaded); corrupted['fixture.png']['sha256'] = 'c' * 64
        with self.assertRaises(ValueError):
            verified_uploads({'entries': [entry]}, observed, corrupted)


if __name__ == '__main__':
    unittest.main()
