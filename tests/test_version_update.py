import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import version_review, verify
from tools.game_resources import files_in
from tools.game_resources.selection import DiscoveryPaths
from tools.hunter_cli.bulk import commit_pass, covers_daily, discovery_queries, merge_outputs, recorded_passes, visible_count


class VersionUpdateTests(unittest.TestCase):
    def test_complete_hunter_receipt_rejects_an_ambiguous_daily_dependency(self):
        from tools.version_update import resources
        from tools.hunter_cli.bulk import KINDS
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder).resolve()
            options = dict(types=list(KINDS), profile='full', queries=[''])
            receipt = dict(status='completed', source_directory=str(session/'export'),
                           source_metadata=str(session/'source.json'), source={'index': {'sha256': 'a'*64}, 'game_build': '1'},
                           options=options, passes=[dict(status='committed', types=list(KINDS), query='')])
            (session/'export.json').write_text(json.dumps(receipt))
            (session/'source.json').write_text(json.dumps(dict(coverage=options, source_container_sha256='a'*64, game_build='1')))
            conflict = 'images/hunter/art/same.png'

            def plan(*args, coverage_check, **kwargs):
                coverage_check({'discovery_directories': ['images/hunter/baked/ui']}, set())
                for roots, paths in (([], {conflict.upper()}), (['images/hunter/art'], set())):
                    with self.assertRaisesRegex(ValueError, 'DAILY_IMAGE_NAME_AMBIGUOUS'):
                        coverage_check({'discovery_directories': roots}, paths)
                raise StopIteration

            with patch('tools.game_resources.make_plan', side_effect=plan), \
                 patch('tools.hunter_cli.bulk.known_image_collisions', return_value={conflict: 2}), \
                 self.assertRaises(StopIteration):
                resources(session, session, session/'plan')

    def test_unregistered_discovery_and_registered_outlier_survive_pruning(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            paths = ['raw_files/hunter/game system data/new.mitem', 'images/world/used.png',
                     'images/world/unregistered.png', 'raw_files/hunter/baked_maps/scene.mbucket']
            for name in paths:
                path = folder/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'x')
            dirs = ['raw_files/hunter/game system data']
            wanted = ['images/world/used.png']
            src = DiscoveryPaths(dirs, wanted)
            self.assertEqual({n for n, _, _ in files_in(folder, discovery=src)}, set(paths[:2]))
            spec = {'discovery_directories': dirs, 'export_terms': ['game system data']}
            self.assertEqual(discovery_queries(spec, wanted, ['raw_files', 'images']), [''])
            self.assertEqual(discovery_queries(spec, wanted, ['raw_files']), ['game system data'])
            self.assertEqual(discovery_queries(spec, wanted, ['materials']), [])

    def test_daily_batches_cover_new_files_and_sparse_inputs_with_old_or_wide_receipts(self):
        spec = {'discovery_directories': ['raw_files/rogue/game system data'],
                'export_terms': ['game system data', 'faceman', 'skillscript', 'mbucket']}
        required = ['raw_files/hunter/skillscript/a', 'raw_files/snowdrop/faceman/skillscript_icon',
                    'raw_files/hunter/baked_maps/map/ts[-40,0,600]_b[0].mbucket.decompiled']
        kinds = ['raw_files', 'images', 'materials']
        terms = discovery_queries(spec, required, kinds)
        self.assertEqual(terms, ['game system data', 'skillscript', 'mbucket'])
        passes = [dict(types=kinds,query=t) for t in terms]
        self.assertTrue(covers_daily(spec,required,kinds,passes))
        old = passes[:-1] + [dict(types=['raw_files'],query='ts[-40',status='committed',
                                  attempts=[dict(applied_query='-40')])]
        self.assertTrue(covers_daily(spec,required,kinds,old))
        old[-1]['types'] = ['images']
        self.assertFalse(covers_daily(spec,required,kinds,old))
        self.assertFalse(covers_daily(spec,required,kinds,passes[1:]))
        unknown = [*required, 'materials/elsewhere/new']
        self.assertEqual(discovery_queries(spec,unknown,kinds), [''])
        self.assertFalse(covers_daily(spec,unknown,kinds,passes))
        self.assertTrue(covers_daily(spec,unknown,kinds,[dict(types=kinds,query='')]))

    def test_new_registration_can_reinstate_a_wider_filter(self):
        spec = dict(discovery_directories=[], export_terms=['/weapons/', 'w_camo_', 'g36'])
        current = ['images/hunter/weapons/w_camo_blue.png', 'raw_files/hunter/weapons/skin_g36.bk2']
        self.assertEqual(discovery_queries(spec,current,['images','raw_files']), ['w_camo_', 'g36'])
        current.append('images/hunter/weapons/new_model.png')
        self.assertEqual(discovery_queries(spec,current,['images','raw_files']), ['/weapons/'])
        suffix = dict(discovery_directories=[], export_terms=['decompiled', 'png'])
        self.assertEqual(discovery_queries(suffix,['raw_files/hunter/unknown.mitem.decompiled',
            'images/hunter/other.png'],['images','raw_files']), [''])

    def test_legacy_single_filter_is_inherited_from_receipt_options(self):
        row = dict(types=['raw_files'], status='committed')
        state = dict(options={'query':'skillscript'},passes=[row])
        self.assertEqual(recorded_passes(state)[0]['query'],'skillscript')
        spec = dict(discovery_directories=['raw_files/hunter/game system data'])
        self.assertFalse(covers_daily(spec,[],['raw_files'],state['passes']))
        with self.assertRaisesRegex(ValueError,'MISSING_EXPORT_PASS_QUERY'):
            recorded_passes(dict(options={'queries':['aa','bb']},passes=[{'types':['raw_files']}]))

    def test_commit_replays_a_rename_without_acknowledging_missing_data(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp).resolve()
            row = {'attempts': [{'directory': 'attempt-1'}], 'output': 'attempt-1/outputs'}
            src = session/row['output']
            src.mkdir(parents=True)
            (src/'x').write_bytes(b'hello')
            (src/'.hunter-commit-attempt-1').touch()
            marker = commit_pass(row, session)
            self.assertEqual((session/'export/x').read_bytes(), b'hello')
            self.assertEqual(commit_pass(row, session), marker)
            marker.unlink()
            with self.assertRaisesRegex(ValueError, 'MARKER_MISSING'):
                commit_pass(row, session)
            with self.assertRaisesRegex(ValueError, 'INVALID_EXPORT'):
                commit_pass(dict(row, output='export'),session)

    def test_overlapping_export_checks_bytes_before_discarding_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp).resolve()
            for name in ('a', 'b'):
                (session/name).mkdir()
                (session/name/'same').write_bytes(b'x')
            (session/'a/extra').write_bytes(b'good')
            merge_outputs(session/'a',session/'b',session)
            self.assertEqual((session/'b/extra').read_bytes(),b'good')
            (session/'a').mkdir()
            (session/'a/same').write_bytes(b'y')
            with self.assertRaisesRegex(ValueError,'CONFLICTING'):
                merge_outputs(session/'a',session/'b',session)
            self.assertEqual((session/'b/same').read_bytes(),b'x')

    def test_hunter_counts_and_duplicate_talent_observations(self):
        self.assertEqual(visible_count('Showing 1,2O0 assets out of 55,OOO loaded'),(1200,55000))
        self.assertEqual(visible_count('2247284 assets loaded'),(2247284,2247284))
        row = dict(entity='a',source='container',slot=['name',0],old_target='a',new_target='b')
        result = version_review.talent_references([row, row.copy()])
        self.assertEqual((result['observations'], result['distinct_slots'], result['changed_talent_targets']),(2,1,1))
        with self.assertRaisesRegex(ValueError,'Conflicting'):
            version_review.talent_references([row,dict(row,new_target='another')])
        unknown = version_review.unknowns([{'x':1},{'x':2}],[{'x':2},{'x':3}])
        self.assertEqual(unknown,dict(introduced=[{'x':3}],resolved=[{'x':1}],carried=[{'x':2}]))

    @unittest.skipUnless(os.name=='nt','Windows configuration lock')
    def test_first_run_guard_removes_only_its_temporary_configuration(self):
        from tools.hunter_cli import __main__ as hunter
        with tempfile.TemporaryDirectory() as temp:
            session=Path(temp)
            config=session/'settings/hunter.dat'
            exe=session/'fixture.exe'
            exe.write_bytes(b'not the pinned binary')
            with patch.object(hunter,'config_path',return_value=config):
                with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED_HUNTER_BINARY'):
                    with hunter.ProtectedHunter(exe,session,allow_missing_config=True):
                        self.fail('unrecognised binary started')
                self.assertFalse(config.exists())
                config.write_bytes(b'original settings')
                with self.assertRaisesRegex(RuntimeError,'UNSUPPORTED_HUNTER_BINARY'):
                    with hunter.ProtectedHunter(exe,session,allow_missing_config=True):
                        self.fail('unrecognised binary started')
                self.assertEqual(config.read_bytes(),b'original settings')

    def test_preflight_failure_stops_before_regression_or_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'dist').mkdir()
            def fail(_root,_out,_env,name,cmd):
                return {'name':name,'skipped':0,'exit_code':int(name=='version-smoke')}
            with patch.object(verify,'ROOT',root), patch.object(verify,'run_step',side_effect=fail):
                self.assertEqual(verify.main(['--output','dist/check']),1)
            receipt = json.loads((root/'dist/check/result.json').read_bytes())
            self.assertFalse(receipt['passed'])
            self.assertEqual([r['name'] for r in receipt['checks']], ['dependencies','identity','version-smoke'])
            self.assertIn('python-tests',receipt['not_run'])
            self.assertIn('publish-build',receipt['not_run'])

