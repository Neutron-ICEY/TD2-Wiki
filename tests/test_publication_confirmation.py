import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.publish.bundle import PublishError, assess_remote, build, digest, load_state, title_key


class PublicationConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_PUBLICATION_CONFIRMATION_TEST_TMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.baseline = self.root / 'publishing/baseline.json'
        self.receipt = self.root / 'publishing/history/receipt.json'
        self.observation = {'title': 'Template:Example', 'namespace': 10, 'revision_id': 101,
                            'content_hash': digest(b'example\n'), 'status': 'PUBLISHED_VERIFIED',
                            'observed_at': '2026-11-02T05:06:06.392Z'}
        self.proof = {'schema_version': 1, 'target': 'test-wiki', 'status': 'PUBLISHED_VERIFIED',
                      'entries': [copy.deepcopy(self.observation)]}
        self.row = {key: self.observation[key] for key in ('title', 'namespace', 'revision_id', 'content_hash')}
        self.row.update(reviewed_by='reviewer', published_at=None,
                        confirmation={'observed_at': self.observation['observed_at'],
                                      'receipt': 'publishing/history/receipt.json', 'receipt_sha256': ''})
        self.save_receipt()

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def save_receipt(self):
        self.write_json(self.receipt, self.proof)
        self.row['confirmation']['receipt_sha256'] = digest(self.receipt.read_bytes())

    def load(self, root=True):
        self.write_json(self.baseline, {'schema_version': 1, 'target': 'test-wiki', 'entries': [self.row]})
        return load_state(self.baseline, 'test-wiki', root=self.root if root else None)

    def test_verified_entries_receipt_accepts_unknown_publication_time(self):
        before = copy.deepcopy(self.row)
        loaded = self.load()[title_key(self.row['title'], self.row['namespace'])]
        self.assertEqual(loaded, before)
        self.assertIsNone(loaded['published_at'])
        self.assertNotIn('observed_at', loaded)

    def test_verified_completed_receipt_is_supported(self):
        self.proof['completed'] = self.proof.pop('entries')
        self.save_receipt()
        self.assertEqual(len(self.load()), 1)

    def test_known_publication_time_keeps_existing_contract(self):
        self.row['published_at'] = '2026-11-02T04:00:00Z'
        self.row.pop('confirmation')
        self.assertEqual(len(self.load(root=False)), 1)

    def test_known_publication_time_requires_valid_date_and_timezone(self):
        self.row.pop('confirmation')
        for value in ('unknown-date', '2026-02-30T10:00:00Z', '2026-11-02',
                      '2026-11-02T04:00:00', True):
            with self.subTest(value=value):
                self.row['published_at'] = value
                with self.assertRaisesRegex(PublishError, 'published_at'):
                    self.load()

    def test_missing_publication_time_does_not_fall_back_to_observed_at(self):
        self.row.pop('published_at')
        self.row['observed_at'] = self.observation['observed_at']
        with self.assertRaisesRegex(PublishError, '缺少人工审核记录'):
            self.load()

    def test_empty_publication_time_cannot_use_confirmation(self):
        self.row['published_at'] = ''
        with self.assertRaisesRegex(PublishError, '缺少人工审核记录'):
            self.load()

    def test_explicit_root_required_for_confirmation(self):
        with self.assertRaisesRegex(PublishError, '显式指定工程 root'):
            self.load(root=False)

    def test_reviewer_is_still_required(self):
        self.row.pop('reviewed_by')
        with self.assertRaisesRegex(PublishError, '缺少人工审核记录'):
            self.load()
        for value in ['   ', True]:
            self.row['reviewed_by']=value
            with self.assertRaisesRegex(PublishError,'缺少人工审核记录'):
                self.load()

    def test_confirmation_must_be_complete(self):
        original = copy.deepcopy(self.row['confirmation'])
        for field in original:
            with self.subTest(field=field):
                self.row['confirmation'] = {key: value for key, value in original.items() if key != field}
                with self.assertRaisesRegex(PublishError, '必须完整记录'):
                    self.load()

    def test_existing_observed_at_cannot_conflict_with_confirmation(self):
        self.row['observed_at'] = '2026-11-02T05:06:07.392Z'
        with self.assertRaisesRegex(PublishError, 'observed_at 不一致'):
            self.load()

    def test_existing_receipt_cannot_conflict_with_confirmation(self):
        self.row['receipt'] = 'publishing/history/other.json'
        with self.assertRaisesRegex(PublishError, 'receipt 不一致'):
            self.load()

    def test_confirmation_time_requires_timezone_and_exact_receipt_match(self):
        for value in ('now', '2026-11-02', '2026-11-02T05:06:06', '2026-11-02T05:06:07.392Z'):
            with self.subTest(value=value):
                self.row['confirmation']['observed_at'] = value
                with self.assertRaises(PublishError):
                    self.load()

    def test_receipt_file_missing_is_not_confirmation(self):
        self.receipt.unlink()
        with self.assertRaises(OSError):
            self.load()

    def test_receipt_bytes_tamper_is_rejected(self):
        with self.receipt.open('ab') as stream:
            stream.write(b' ')
        with self.assertRaisesRegex(PublishError, 'SHA-256 不匹配'):
            self.load()

    def test_receipt_target_schema_and_status_are_checked(self):
        original = copy.deepcopy(self.proof)
        for field, value in (('target', 'other-wiki'), ('status', 'LOCAL_CANDIDATE'), ('schema_version', 2)):
            with self.subTest(field=field):
                self.proof = {**original, field: value}
                self.save_receipt()
                with self.assertRaisesRegex(PublishError, '未确认发布或目标不匹配'):
                    self.load()

    def test_receipt_entry_identity_must_match_exactly(self):
        replacements = {'title': 'Template:Other', 'namespace': 0, 'revision_id': 102,
                        'content_hash': digest(b'other'), 'observed_at': '2026-11-02T05:06:07.392Z',
                        'status': 'PENDING'}
        for field, value in replacements.items():
            with self.subTest(field=field):
                self.proof['entries'] = [{**self.observation, field: value}]
                self.save_receipt()
                with self.assertRaises(PublishError):
                    self.load()

    def test_duplicate_target_is_rejected_even_if_only_one_revision_matches(self):
        self.proof['entries'].append({**self.observation, 'revision_id': 100})
        self.save_receipt()
        with self.assertRaisesRegex(PublishError, '唯一匹配'):
            self.load()

    def test_duplicate_across_entries_and_completed_is_rejected(self):
        self.proof['completed'] = [copy.deepcopy(self.observation)]
        self.save_receipt()
        with self.assertRaisesRegex(PublishError, '唯一匹配'):
            self.load()

    def test_normalized_title_alias_does_not_replace_exact_identity(self):
        self.proof['entries'][0]['title'] = '模板:Example'
        self.save_receipt()
        with self.assertRaisesRegex(PublishError, '确认内容不匹配'):
            self.load()

    def test_receipt_must_stay_in_history(self):
        for value in ('other.json', 'publishing/history/../../outside.json',
                      '../outside.json', 'publishing\\history\\receipt.json'):
            with self.subTest(value=value):
                self.row['confirmation']['receipt'] = value
                with self.assertRaises(PublishError):
                    self.load()

    def test_receipt_duplicate_json_keys_are_rejected(self):
        self.receipt.write_text('{"schema_version":1,"schema_version":1}', encoding='utf-8')
        self.row['confirmation']['receipt_sha256'] = digest(self.receipt.read_bytes())
        with self.assertRaisesRegex(PublishError, '重复 JSON 字段'):
            self.load()

    def test_asset_still_requires_exact_file_revision(self):
        self.row.update(title='File:Example.png', namespace=6, file_revision='upload-1')
        self.proof['entries'] = [{**self.observation, 'title': self.row['title'], 'namespace': 6,
                                  'file_revision': 'upload-1'}]
        self.save_receipt()
        self.assertEqual(len(self.load()), 1)
        self.proof['entries'][0]['file_revision'] = 'upload-2'
        self.save_receipt()
        with self.assertRaisesRegex(PublishError, '资产版本不匹配'):
            self.load()
        self.proof['entries'][0].pop('file_revision')
        self.row.pop('file_revision')
        self.save_receipt()
        with self.assertRaisesRegex(PublishError, '资产 state 必须记录 file_revision'):
            self.load()

    def test_snapshot_contract_does_not_use_baseline_confirmation(self):
        self.write_json(self.baseline, {'schema_version': 1, 'target': 'test-wiki', 'entries': [{
            **self.row, 'exists': True, 'observed_at': self.observation['observed_at']}]})
        self.assertEqual(len(load_state(self.baseline, 'test-wiki', snapshot=True)), 1)

    def test_confirmed_baseline_still_reports_unverified_remote_and_drift(self):
        self.load()
        source = self.root / 'wiki/templates/example.wiki'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'example\n')
        registry = self.root / 'publishing/registry.json'
        self.write_json(registry, {'schema_version': 1, 'target': 'test-wiki', 'mode': 'MANUAL',
                                  'namespace_prefixes': {'10': ['Template']}, 'entries': [{
                                      'id': 'example', 'kind': 'templates', 'namespace': 10,
                                      'title': self.row['title'], 'source': 'wiki/templates/example.wiki',
                                      'ownership': 'manual', 'related_entity': None,
                                      'change_reason': 'fixture', 'asset_relationships': []}]})
        manifest = build(self.root, registry, self.baseline, self.root / 'dist/confirmed')
        self.assertEqual(manifest['entries'][0]['operation'], 'unchanged')
        self.assertEqual(manifest['entries'][0]['conflicts'], ['REMOTE_UNVERIFIED'])
        remote = {**self.row, 'exists': True, 'revision_id': 102}
        self.assertEqual(assess_remote(self.row, remote), 'REMOTE_DRIFT')

    def test_receipt_junction_is_rejected_inside_or_outside_history(self):
        for target in (self.root / 'external-proof', self.root / 'publishing/history/actual'):
            target.mkdir(parents=True)
            self.write_json(target / 'receipt.json', self.proof)
            link = self.root / 'publishing/history/link'
            if os.name == 'nt':
                import _winapi
                _winapi.CreateJunction(str(target), str(link))
            else:
                link.symlink_to(target, target_is_directory=True)
            try:
                self.row['confirmation']['receipt'] = 'publishing/history/link/receipt.json'
                with self.assertRaises(PublishError):
                    self.load()
            finally:
                link.rmdir() if os.name == 'nt' else link.unlink()


if __name__ == '__main__':
    unittest.main()
