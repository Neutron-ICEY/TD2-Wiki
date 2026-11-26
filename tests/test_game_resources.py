from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import game_resources as resources


class Interrupted(BaseException):
    pass


class GameResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_GAME_RESOURCES_TEST_TMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.store = self.root / 'resources/game'
        self.current = self.store / 'current'
        self.current.mkdir(parents=True)
        self.source = self.root / 'incoming/update'
        self.source.mkdir(parents=True)
        self.plan = self.root / 'dist/update'
        self.old_source = {'source_id': 'old', 'origin': 'manual export', 'game_build': None,
                           'source_container_sha256': 'a' * 64}
        self.new_source = {'source_id': 'new', 'origin': 'manual export', 'game_build': 'fixture-build',
                           'source_container_sha256': 'b' * 64}
        self.put(self.current, 'raw_files/hunter/changed.item', b'before')
        self.put(self.current, 'images/hunter/unchanged.png', b'unchanged')
        self.put(self.current, 'raw_files/hunter/omitted.item', b'keep in partial')
        self.put(self.root, 'data/manual.json', b'{"manual":true}')
        resources.initialize(self.root, self.old_source)

    def put(self, root, relative, content):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def prepare(self, full=False):
        self.put(self.source, 'raw_files/hunter/changed.item', b'after')
        self.put(self.source, 'raw_files/hunter/new.item', b'new')
        self.put(self.source, 'images/hunter/unchanged.png', b'unchanged')
        return resources.make_plan(self.root, self.source, self.new_source, self.plan,
                                   ['raw_files'] if full else [])

    def current_bytes(self):
        return {name: path.read_bytes() for name, path, _ in resources.files_in(self.current)}

    def test_partial_changes_keep_omitted_files_and_unchanged_identity(self):
        old = (self.current / 'images/hunter/unchanged.png').stat()
        report = self.prepare()
        self.assertEqual(report['changes'], {'added': 1, 'modified': 1, 'deleted': 0,
                                            'unchanged': 1, 'retained': 1, 'copy_bytes': 8})
        self.assertEqual(resources.apply_plan(self.root, self.plan)['status'], 'applied')
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        self.assertEqual((self.current / 'raw_files/hunter/omitted.item').read_bytes(), b'keep in partial')
        same = (self.current / 'images/hunter/unchanged.png').stat()
        self.assertEqual((old.st_ino, old.st_mtime_ns), (same.st_ino, same.st_mtime_ns))
        self.assertEqual((self.root / 'data/manual.json').read_bytes(), b'{"manual":true}')
        self.assertEqual(resources.status(self.root, True)['source_counts'], {'new': 3, 'old': 1})
        self.assertFalse((self.store / '.transaction').exists())
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)

    def test_complete_scope_deletion_requires_explicit_flag(self):
        self.prepare(full=True)
        before = self.current_bytes()
        with self.assertRaisesRegex(resources.ResourceError, 'DELETIONS_REQUIRE'):
            resources.apply_plan(self.root, self.plan)
        self.assertEqual(before, self.current_bytes())
        resources.apply_plan(self.root, self.plan, allow_deletions=True)
        self.assertFalse((self.current / 'raw_files/hunter/omitted.item').exists())
        self.assertTrue((self.current / 'images/hunter/unchanged.png').is_file())
        resources.status(self.root, True)

    def test_missing_complete_directory_does_not_delete(self):
        with self.assertRaisesRegex(resources.ResourceError, 'COMPLETE_SCOPE_DIRECTORY_MISSING'):
            resources.make_plan(self.root, self.source, self.new_source, self.plan, ['raw_files'])
        self.assertFalse(self.plan.exists())

    def test_empty_complete_directory_removed_after_plan_does_not_delete(self):
        (self.source / 'raw_files').mkdir()
        resources.make_plan(self.root, self.source, self.new_source, self.plan, ['raw_files'])
        before = self.current_bytes()
        (self.source / 'raw_files').rmdir()
        with self.assertRaisesRegex(resources.ResourceError, 'COMPLETE_SCOPE_DIRECTORY_MISSING'):
            resources.apply_plan(self.root, self.plan, True)
        self.assertEqual(before, self.current_bytes())
        self.assertFalse((self.store / '.transaction').exists())


    def test_changed_source_drift_fails_and_same_plan_can_retry(self):
        self.prepare()
        changed = self.put(self.source, 'raw_files/hunter/changed.item', b'other')
        with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_CONTENT_DRIFT'):
            resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'before')
        self.assertFalse((self.store / 'updates').exists())
        with self.assertRaisesRegex(resources.ResourceError, 'PENDING_TRANSACTION'):
            resources.status(self.root)
        changed.write_bytes(b'after')
        resources.apply_plan(self.root, self.plan)
        resources.status(self.root, True)

    def test_plan_freezes_import_set_and_later_source_changes_wait_for_next_plan(self):
        self.prepare()
        self.put(self.source, 'zz/new.file', b'late')
        self.put(self.source, 'images/hunter/unchanged.png', b'edited after planning')
        resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.current / 'zz/new.file').exists())
        self.assertEqual((self.current / 'images/hunter/unchanged.png').read_bytes(), b'unchanged')
        resources.status(self.root, True)
        result = resources.make_plan(self.root, self.source, self.new_source, self.root / 'dist/later')
        self.assertEqual(result['changes']['added'], 1)
        self.assertEqual(result['changes']['modified'], 1)

    def test_partial_update_preserves_unrelated_file_and_full_verify_detects_its_drift(self):
        self.prepare()
        self.put(self.current, 'raw_files/hunter/omitted.item', b'out of band edit')
        resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.current/'raw_files/hunter/omitted.item').read_bytes(),b'out of band edit')
        with self.assertRaisesRegex(resources.ResourceError,'RESOURCE_CONTENT_DRIFT'):
            resources.status(self.root,True)

    def test_source_id_cannot_be_reassigned(self):
        with self.assertRaisesRegex(resources.ResourceError, 'SOURCE_ID_METADATA_CONFLICT'):
            resources.make_plan(self.root, self.source, {**self.new_source, 'source_id': 'old'}, self.plan)

    def test_plan_edits_are_rejected(self):
        self.prepare()
        plan = resources.read_json(self.plan / 'plan.json')
        plan['summary']['changes']['added'] = 5
        (self.plan / 'plan.json').write_bytes(resources.encoded(plan))
        with self.assertRaisesRegex(resources.ResourceError, 'PLAN_CHANGED'):
            resources.apply_plan(self.root, self.plan)

    def test_artifact_edits_are_rejected(self):
        self.prepare()
        with (self.plan / 'operations.jsonl').open('ab') as stream:
            stream.write(b'{}\n')
        with self.assertRaisesRegex(resources.ResourceError, 'PLAN_ARTIFACT_CHANGED'):
            resources.apply_plan(self.root, self.plan)

    def test_path_escape_is_rejected_even_with_rehashed_plan(self):
        self.prepare()
        rows = list(resources.read_operations(self.plan / 'operations.jsonl'))
        rows[0]['path'] = '../../data/manual.json'
        (self.plan / 'operations.jsonl').write_bytes(b''.join(resources.encoded(row) for row in rows))
        plan = resources.read_json(self.plan / 'plan.json')
        plan['artifacts']['operations.jsonl'] = resources.digest(self.plan / 'operations.jsonl')
        (self.plan / 'plan.json').write_bytes(resources.encoded(plan))
        (self.plan / 'plan.sha256').write_text(resources.digest(self.plan / 'plan.json'))
        with self.assertRaisesRegex(resources.ResourceError, 'INVALID_RESOURCE_PATH'):
            resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.root / 'data/manual.json').read_bytes(), b'{"manual":true}')

    def test_duplicate_native_paths_are_reported_and_preserved(self):
        self.put(self.source, 'raw_files/hunter/a.item', b'duplicate')
        self.put(self.source, 'raw_files/rogue/b.item', b'duplicate')
        result = resources.make_plan(self.root, self.source, self.new_source, self.plan, report_duplicates=True)
        self.assertEqual(result['duplicates']['files'], 1)
        self.assertEqual(result['duplicates']['bytes'], 9)
        resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.current / 'raw_files/hunter/a.item').read_bytes(),
                         (self.current / 'raw_files/rogue/b.item').read_bytes())

    def interrupt_on_new_install(self, exception):
        original = os.replace
        def replacement(source, destination):
            if Path(destination) == self.current / 'raw_files/hunter/new.item':
                raise exception
            return original(source, destination)
        return patch.object(resources.os, 'replace', side_effect=replacement)

    def test_io_failure_stays_pending_and_retry_replays_changes_and_deletions(self):
        self.prepare(full=True)
        with self.interrupt_on_new_install(OSError('disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                resources.apply_plan(self.root, self.plan, True)
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        self.assertFalse((self.store / '.transaction/old').exists())
        self.assertFalse((self.store / 'updates').exists())
        with self.assertRaisesRegex(resources.ResourceError, 'PENDING_TRANSACTION'):
            resources.status(self.root)
        resources.recover(self.root)
        self.assertFalse((self.current / 'raw_files/hunter/omitted.item').exists())
        self.assertEqual((self.current / 'raw_files/hunter/new.item').read_bytes(), b'new')
        resources.status(self.root, True)

    def test_interrupted_process_can_retry_before_commit(self):
        self.prepare(full=True)
        with self.interrupt_on_new_install(Interrupted()):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan, True)
        with self.assertRaisesRegex(resources.ResourceError, 'PENDING_TRANSACTION'):
            resources.status(self.root)
        self.assertEqual(resources.recover(self.root)['previous_state'], 'applying')
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        resources.status(self.root, True)

    def test_cleanup_failure_after_commit_preserves_success(self):
        self.prepare()
        with patch.object(resources, 'remove_transaction', side_effect=OSError('cleanup failure')):
            with self.assertRaisesRegex(OSError, 'cleanup failure'):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        self.assertEqual(resources.recover(self.root)['previous_state'], 'committed')
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)
        resources.status(self.root, True)

    def interrupt_after_transaction_file_removal(self, name):
        original = Path.unlink
        target = self.store / '.transaction' / name
        def interrupted(path, *args, **kwargs):
            result = original(path, *args, **kwargs)
            if path == target:
                raise Interrupted()
            return result
        return patch.object(Path, 'unlink', new=interrupted)


    def test_interruption_after_final_state_removal_leaves_only_empty_transaction(self):
        self.prepare()
        with self.interrupt_after_transaction_file_removal('state.json'):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual(list((self.store / '.transaction').iterdir()), [])
        self.assertEqual(resources.recover(self.root)['previous_state'], 'not_started')
        self.assertFalse((self.store / '.transaction').exists())
        self.assertEqual(resources.status(self.root, True)['source_counts'], {'new': 3, 'old': 1})


    def test_receipt_transfer_interruption_preserves_committed_update(self):
        self.prepare()
        original = os.replace
        def transferred(source, target):
            result = original(source, target)
            if Path(source) == self.store / '.transaction/receipt.json':
                raise Interrupted()
            return result
        with patch.object(resources.os, 'replace', side_effect=transferred):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.store / '.transaction/receipt.json').exists())
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)
        self.assertEqual(resources.read_json(self.store / '.transaction/state.json')['state'], 'committed')
        self.assertEqual(resources.recover(self.root)['previous_state'], 'committed')
        self.assertEqual(resources.status(self.root, True)['source_counts'], {'new': 3, 'old': 1})

    def test_receipt_duplicate_removal_interruption_can_resume_cleanup(self):
        self.prepare()
        with patch.object(resources, 'finish_receipt', side_effect=Interrupted()):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        pending = self.store / '.transaction/receipt.json'
        receipt = resources.read_json(pending)
        self.put(self.store, 'updates/' + receipt['receipt_id'] + '.json', pending.read_bytes())
        with self.interrupt_after_transaction_file_removal('receipt.json'):
            with self.assertRaises(Interrupted):
                resources.recover(self.root)
        self.assertFalse(pending.exists())
        self.assertEqual(resources.read_json(self.store / '.transaction/state.json')['state'], 'committed')
        self.assertEqual(resources.recover(self.root)['previous_state'], 'committed')
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)
        self.assertEqual(resources.status(self.root, True)['source_counts'], {'new': 3, 'old': 1})

    def test_receipt_failure_after_commit_is_recovered_as_success(self):
        self.prepare()
        with patch.object(resources, 'finish_receipt', side_effect=OSError('receipt failure')):
            with self.assertRaisesRegex(OSError, 'receipt failure'):
                resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.store / 'updates').exists())
        self.assertEqual(resources.recover(self.root)['previous_state'], 'committed')
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)
        resources.status(self.root, True)

    def test_retry_replaces_reexportable_raw_but_preserves_all_manual_sources(self):
        for name in ('wiki/page.wikitext', 'assets/image.png', 'data/map.json', 'tools/manual.py'):
            self.put(self.root, name, b'human work')
        self.prepare()
        with self.interrupt_on_new_install(Interrupted()):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        self.put(self.current, 'raw_files/hunter/changed.item', b'failed export')
        resources.recover(self.root)
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'after')
        for name in ('wiki/page.wikitext', 'assets/image.png', 'data/map.json', 'tools/manual.py'):
            self.assertEqual((self.root / name).read_bytes(), b'human work')

    def check_recovery_metadata_edit(self, name):
        self.prepare()
        with self.interrupt_on_new_install(Interrupted()):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        path = self.store / name
        original = path.read_bytes()
        path.write_bytes(original + b'\n')
        before = self.current_bytes()
        with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_METADATA_CHANGED'):
            resources.recover(self.root)
        self.assertEqual(before, self.current_bytes())
        self.assertEqual(path.read_bytes(), original + b'\n')
        path.write_bytes(original)
        resources.recover(self.root)
        resources.status(self.root, True)

    def test_recovery_preserves_unrelated_source_metadata_edit(self):
        self.check_recovery_metadata_edit('source.json')

    def test_recovery_preserves_unrelated_manifest_edit(self):
        self.check_recovery_metadata_edit('manifest.jsonl')

    def test_metadata_changed_during_copy_prevents_commit(self):
        self.prepare()
        original = resources.copy_verified
        def changing(*args):
            result = original(*args)
            with (self.store / 'source.json').open('ab') as stream:
                stream.write(b'\n')
            return result
        with patch.object(resources, 'copy_verified', side_effect=changing):
            with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_METADATA_CHANGED'):
                resources.apply_plan(self.root, self.plan)
        self.assertFalse((self.store / 'updates').exists())
        self.assertTrue((self.store / '.transaction').exists())

    def junction(self, target, path):
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(target), str(path))
        else:
            path.symlink_to(target, target_is_directory=True)
        self.addCleanup(lambda: path.rmdir() if os.name == 'nt' else path.unlink())

    def test_source_directory_link_is_rejected(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.put(outside, 'secret.item', b'not an export')
        self.junction(outside, self.source / 'link')
        with self.assertRaisesRegex(resources.ResourceError, 'LINK_NOT_ALLOWED'):
            resources.make_plan(self.root, self.source, self.new_source, self.plan)

    def test_current_parent_link_substitution_is_rejected(self):
        self.prepare()
        existing = self.current / 'raw_files/hunter'
        outside = self.root / 'outside'
        existing.rename(outside)
        self.junction(outside, existing)
        with self.assertRaisesRegex(resources.ResourceError, 'LINK_NOT_ALLOWED'):
            resources.apply_plan(self.root, self.plan)
        self.assertEqual((outside / 'changed.item').read_bytes(), b'before')

    def test_manifest_status_is_not_a_content_verification(self):
        self.put(self.current, 'raw_files/hunter/changed.item', b'out of band')
        self.assertFalse(resources.status(self.root)['content_checked'])
        with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_CONTENT_DRIFT'):
            resources.status(self.root, True)

    def test_exclusive_lock_blocks_other_update(self):
        self.prepare()
        with resources.locked(self.store):
            with self.assertRaisesRegex(resources.ResourceError, 'RESOURCE_LIBRARY_BUSY'):
                resources.apply_plan(self.root, self.plan)

    def test_stale_plan_after_success_is_rejected(self):
        self.prepare()
        resources.apply_plan(self.root, self.plan)
        with self.assertRaisesRegex(resources.ResourceError, 'STALE_RESOURCE_PLAN'):
            resources.apply_plan(self.root, self.plan)

    def test_cli_accepts_root_after_command(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(resources.main(['status', '--root', str(self.root)]), 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'manifest_validated')

    def test_initialization_interruption_resets_metadata_without_touching_raw(self):
        root = self.root / 'new-project'
        current = root / 'resources/game/current'
        self.put(current, 'raw_files/hunter/original.item', b'original')
        original = os.replace
        def replacement(source, target):
            if Path(target) == root / 'resources/game/source.json':
                raise Interrupted()
            return original(source, target)
        with patch.object(resources.os, 'replace', side_effect=replacement):
            with self.assertRaises(Interrupted):
                resources.initialize(root, self.old_source)
        self.assertEqual(resources.recover(root)['status'], 'initialization_reset')
        self.assertEqual((current / 'raw_files/hunter/original.item').read_bytes(), b'original')
        self.assertFalse((root / 'resources/game/manifest.jsonl').exists())
        resources.initialize(root, self.old_source)
        self.assertEqual(resources.status(root, True)['files'], 1)

    def test_truncated_first_initialization_marker_recovers(self):
        for exception in (OSError('marker write failed'), Interrupted()):
            with self.subTest(exception=type(exception).__name__):
                root = self.root / ('new-' + type(exception).__name__)
                current = root / 'resources/game/current'
                self.put(current, 'raw_files/original', b'original')
                original = resources.write_json
                def failing(path, value):
                    if Path(path) == root / 'resources/game/.initializing.json':
                        Path(path).write_bytes(b'{')
                        raise exception
                    return original(path, value)
                with patch.object(resources, 'write_json', side_effect=failing):
                    with self.assertRaises(type(exception)):
                        resources.initialize(root, self.old_source)
                if isinstance(exception, Interrupted):
                    self.assertEqual(resources.recover(root)['status'], 'initialization_reset')
                self.assertEqual((current / 'raw_files/original').read_bytes(), b'original')
                self.assertFalse((root / 'resources/game/.initializing.json').exists())
                resources.initialize(root, self.old_source)
                self.assertEqual(resources.status(root, True)['files'], 1)

    def test_truncated_initialization_marker_with_metadata_refuses_cleanup(self):
        self.put(self.store, '.initializing.json', b'{')
        before = (self.store / 'source.json').read_bytes()
        with self.assertRaisesRegex(resources.ResourceError, 'INITIALIZATION_STATE_MISSING_WITH_CONTENT'):
            resources.recover(self.root)
        self.assertEqual((self.store / 'source.json').read_bytes(), before)

    def test_streaming_order_handles_file_directory_prefixes(self):
        self.put(self.source, 'raw_files/a.item', b'a')
        self.put(self.source, 'raw_files/a/child.item', b'b')
        self.put(self.source, 'raw_files/a0.item', b'c')
        self.put(self.source, 'raw_files/Z.item', b'd')
        resources.make_plan(self.root, self.source, self.new_source, self.plan)
        names = [row['path'] for row in resources.rows(self.plan / 'incoming.jsonl')]
        self.assertEqual(names, sorted(names, key=str.casefold))
        resources.apply_plan(self.root, self.plan)
        self.assertEqual(resources.status(self.root, True)['files'], 7)

    def test_interrupted_metadata_commit_finishes_without_source(self):
        self.prepare(full=True)
        original = os.replace
        def replacement(source, destination):
            if Path(destination) == self.store / 'source.json':
                raise OSError('metadata commit failed')
            return original(source, destination)
        with patch.object(resources.os, 'replace', side_effect=replacement):
            with self.assertRaisesRegex(OSError, 'metadata commit failed'):
                resources.apply_plan(self.root, self.plan, True)
        self.assertEqual(resources.read_json(self.store / '.transaction/state.json')['state'], 'committing')
        self.source.rename(self.root / 'source-unavailable')
        self.assertEqual(resources.recover(self.root)['previous_state'], 'committing')
        self.assertEqual(resources.status(self.root, True)['source_counts'], {'new': 3})
        self.assertEqual(len(list((self.store / 'updates').glob('*.json'))), 1)

    def test_first_state_write_failure_can_reset_before_touching_raw(self):
        self.prepare()
        before = self.current_bytes()
        original = resources.write_json
        def failure(path, value):
            if Path(path) == self.store / '.transaction/state-next.json':
                raise OSError('first state write failed')
            return original(path, value)
        with patch.object(resources, 'write_json', side_effect=failure):
            with self.assertRaisesRegex(OSError, 'first state write failed'):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual(resources.recover(self.root)['previous_state'], 'not_started')
        self.assertEqual(before, self.current_bytes())
        resources.status(self.root, True)

    def test_interruption_before_first_state_write_can_recover(self):
        self.prepare()
        original = resources.write_json
        def interruption(path, value):
            if Path(path) == self.store / '.transaction/state-next.json':
                raise Interrupted()
            return original(path, value)
        with patch.object(resources, 'write_json', side_effect=interruption):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual(resources.recover(self.root)['previous_state'], 'not_started')
        resources.status(self.root, True)

    def test_missing_state_with_backup_content_refuses_cleanup(self):
        self.put(self.store, '.transaction/old/possibly-original', b'preserve')
        with self.assertRaisesRegex(resources.ResourceError, 'TRANSACTION_STATE_MISSING_WITH_CONTENT'):
            resources.recover(self.root)
        self.assertEqual((self.store / '.transaction/old/possibly-original').read_bytes(), b'preserve')

    def test_default_skips_duplicate_index_and_cli_can_opt_in(self):
        self.put(self.source, 'a', b'duplicate')
        self.put(self.source, 'b', b'duplicate')
        with patch.object(resources.sqlite3, 'connect', side_effect=AssertionError('unexpected duplicate index')):
            result = resources.make_plan(self.root, self.source, self.new_source, self.plan)
        self.assertIsNone(result['duplicates'])
        metadata = self.put(self.root, 'metadata.json', resources.encoded(self.new_source))
        output = io.StringIO()
        with redirect_stdout(output):
            code = resources.main(['plan', '--root', str(self.root), '--source', str(self.source),
                                   '--metadata', str(metadata), '--output', str(self.root / 'dist/duplicates'),
                                   '--unfiltered', '--report-duplicates'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['duplicates']['files'], 1)

    def test_apply_reads_only_changed_inputs_and_no_current_payload(self):
        self.prepare()
        original = Path.open
        reads = []
        def opened(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            if 'r' in mode:
                self.assertFalse(path.is_relative_to(self.current), 'reread current payload')
                if path.is_relative_to(self.source):
                    reads.append(path.relative_to(self.source).as_posix())
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', new=opened):
            result = resources.apply_plan(self.root, self.plan)
        self.assertEqual(reads, ['raw_files/hunter/changed.item', 'raw_files/hunter/new.item'])
        self.assertEqual(result['content_scope'], 'changed_files')
        self.assertEqual(result['timings']['stages']['copy_hash']['bytes'], 8)
        timings = result['timings']
        accounted = sum(row['exclusive_seconds'] for row in timings['stages'].values())
        self.assertAlmostEqual(accounted + timings['unattributed_seconds'], timings['elapsed_seconds'], places=4)

    def test_empty_and_multiblock_copies_and_repeated_apply(self):
        self.put(self.source, 'empty', b'')
        self.put(self.source, 'large', b'12345678' * 300000)
        resources.make_plan(self.root, self.source, self.new_source, self.plan)
        resources.apply_plan(self.root, self.plan)
        resources.status(self.root, True)
        repeated = self.root / 'dist/repeat'
        result = resources.make_plan(self.root, self.source, self.new_source, repeated)
        self.assertEqual(result['changes']['copy_bytes'], 0)
        with patch.object(resources, 'copy_verified', side_effect=AssertionError('copied unchanged file')):
            resources.apply_plan(self.root, repeated)
        resources.status(self.root, True)

    def test_interrupted_copy_preserves_target_and_retry_replaces_temporary(self):
        self.prepare()
        def partial(source, target, expected):
            target.write_bytes(b'partial write')
            raise OSError('copy failure')
        with patch.object(resources, 'copy_verified', side_effect=partial):
            with self.assertRaisesRegex(OSError, 'copy failure'):
                resources.apply_plan(self.root, self.plan)
        self.assertEqual((self.current / 'raw_files/hunter/changed.item').read_bytes(), b'before')
        resources.recover(self.root)
        resources.status(self.root, True)

    def test_pending_update_refuses_other_plan_and_cli_never_reports_success(self):
        self.prepare()
        other = self.root / 'dist/other'
        resources.make_plan(self.root, self.source, self.new_source, other)
        output = io.StringIO()
        with self.interrupt_on_new_install(OSError('disk failure')), redirect_stdout(output):
            self.assertEqual(resources.main(['apply', '--root', str(self.root), '--plan', str(self.plan)]), 2)
        self.assertEqual(output.getvalue(), '')
        with self.assertRaisesRegex(resources.ResourceError, 'PENDING_UPDATE_PLAN_MISMATCH'):
            resources.apply_plan(self.root, other)
        with self.assertRaisesRegex(resources.ResourceError, 'PENDING_TRANSACTION.*applying'):
            resources.status(self.root)
        resources.recover(self.root)

    def test_retry_after_completed_deletion_is_idempotent(self):
        self.prepare(full=True)
        original = resources.check_complete_scopes
        calls = 0
        def fail_after_files(*args):
            nonlocal calls
            calls += 1
            original(*args)
            if calls == 2:
                raise Interrupted()
        with patch.object(resources, 'check_complete_scopes', side_effect=fail_after_files):
            with self.assertRaises(Interrupted):
                resources.apply_plan(self.root, self.plan, True)
        self.assertFalse((self.current / 'raw_files/hunter/omitted.item').exists())
        resources.recover(self.root)
        resources.status(self.root, True)

    def test_old_pending_transaction_is_preserved(self):
        self.put(self.store, '.transaction/state.json', resources.encoded({'state': 'applying'}))
        self.put(self.store, '.transaction/old/original', b'old data')
        with self.assertRaisesRegex(resources.ResourceError, 'UNSUPPORTED_PENDING_UPDATE'):
            resources.recover(self.root)
        self.assertEqual((self.store / '.transaction/old/original').read_bytes(), b'old data')


if __name__ == '__main__':
    unittest.main()
