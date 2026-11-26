from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.equipment import weapon_chart_study as study, weapons


class WeaponChartChecks(unittest.TestCase):
    def test_rebuild_from_frozen_inputs_without_game_or_old_build_directories(self):
        with TemporaryDirectory() as work:
            root=Path(work)
            shutil.copytree(study.ROOT/study.STUDY, root/study.STUDY)
            (root/'data/equipment').mkdir(parents=True)
            mapping = 'data/equipment/native-map.json'
            shutil.copyfile(study.ROOT/mapping, root/mapping)
            catalog=study.rebuild(root)
            models=catalog['models']
            base=models['5d4179f1569771580000db08f5a8cf47']
            lefty=models['f58bdd5662de9d6c0008594bc73a8023']
            self.assertEqual(base['trace'],lefty['trace'])
            self.assertIn(base['trace'],catalog['traces'])
            self.assertEqual(set(base['angles']),{'stand','move','cover','hip','blind'})
            self.assertNotIn('5d4179f15bd9c83400030db924aa0fb5',models)
            special=['346395bc5e16e8b0000fdc00ab5a593a','b00501356ac76779000383006f7cef03',
                     '5d4179f15bd72590000304c3804b3d33','4cdce5b25c5c487f00032719ace78511']
            for uid,shots in zip(special,(20,30,30,30),strict=True):
                model=models[uid]
                self.assertEqual(set(model['angles']),set(base['angles']))
                trace=catalog['traces'][model['trace']]
                self.assertEqual([len(group.split()) for group in trace['groups']],[shots]*8)
                self.assertGreater(len(trace['path'].split()),shots)
            self.assertEqual(models[special[2]]['trace'],models[special[3]]['trace'])
            self.assertEqual(len({models[u]['trace'] for u in special}),3)
            signature = {uid: model for uid, model in models.items() if model['group'] == 'SignatureWeapon'}
            minigun, tac = '028db20a5ca4b93c000352e84077d974', '5d4179f15ad5f40900006e66c5e6ec16'
            self.assertEqual(signature.keys(), {minigun, tac})
            self.assertEqual(set(signature[minigun]['angles']), {'stand', 'move', 'hip'})
            trace = catalog['traces'][signature[minigun]['trace']]
            self.assertEqual(trace['shots'], 30)
            self.assertTrue(trace['returnPath'])
            self.assertNotIn('trace', signature[tac])
            tac_angles = signature[tac]['angles']
            self.assertEqual(set(tac_angles), {'stand', 'move', 'cover', 'blind', 'hip'})
            self.assertAlmostEqual(tac_angles['cover'][0], 0.1, places=6)
            self.assertAlmostEqual(tac_angles['cover'][1], 0.5, places=6)
            for mode in ('hip', 'blind'):
                for angle in tac_angles[mode]:
                    self.assertAlmostEqual(angle, 10.0, places=6)
            self.assertEqual(set(catalog['traces']), {m['trace'] for m in models.values() if 'trace' in m})
            self.assertEqual(catalog['movementSpeed'], 1.9)
            for uid,expected in [('66db060453392ead00000368c62582f6',(0.528125,1.228125)),
                                 ('66db0604535f7c2b00001eaa186eb521',(0.7125,1.0125))]:
                for angle,reference in zip(models[uid]['angles']['move'],expected,strict=True):
                    self.assertAlmostEqual(angle,reference,places=6)
            quickstep = models['b005013568d2660500037195c011fb89']['angles']
            self.assertAlmostEqual(quickstep['move'][0] - quickstep['stand'][0], 1.9 / 302 * 1.75, places=6)
            m1911 = models['66db0604536b6234000000a24d7ed1b1']['angles']
            self.assertEqual(quickstep['move'], m1911['move'])
            pf45=models['66db060453393bf9000002bc3aaf7654']
            self.assertEqual(catalog['traces'][pf45['trace']]['shots'],10)
            self.assertEqual(study.encoded(catalog),(study.ROOT/study.CATALOG).read_bytes())
            archive=root/study.STUDY/'control-observations.zip'
            archive.write_bytes(archive.read_bytes()+b'altered')
            with self.assertRaisesRegex(ValueError,'archive checksum mismatch'):
                study.rebuild(root)

    def test_generation_rejects_restored_and_new_unsupported_signature_models(self):
        catalog = weapons.raw_json(study.ROOT / study.CATALOG)
        crossbow = '5d4179f15a141f2b00001cadf3643af3'
        sample = catalog['models']['028db20a5ca4b93c000352e84077d974']
        for uid in (crossbow, 'a' * 32):
            with self.subTest(uid=uid), patch.dict(catalog['models'], {uid: sample}):
                with patch.object(weapons, 'raw_json', return_value=catalog):
                    with self.assertRaisesRegex(ValueError, 'Unsupported signature weapon in chart catalog: ' + uid):
                        weapons.chart_modules()
        tac = '5d4179f15ad5f40900006e66c5e6ec16'
        with patch.dict(catalog['models'][tac], {'trace': sample['trace']}):
            with patch.object(weapons, 'raw_json', return_value=catalog):
                with self.assertRaisesRegex(ValueError, 'Unsupported signature recoil in chart catalog: ' + tac):
                    weapons.chart_modules()

    def test_check_reports_an_individually_stale_chart_shard(self):
        with TemporaryDirectory() as work:
            root=Path(work)
            inputs=['publishing/registry.json','publishing/baseline.json','data/equipment/records.json',
                    'data/equipment/weapon-charts.json','data/equipment/weapon-navbox-talents.json',
                    'data/brand-sets/equipment-ui.json','data/brand-sets/talents.json']
            targets=['wiki/templates/武器信息.wiki','wiki/templates/TD2武器导航.wiki',
                     *['wiki/modules/TD2武器图表/'+group+'.lua' for group in weapons.GROUPS]]
            targets.extend(path.relative_to(study.ROOT) for path in
                           (study.ROOT/'wiki/redirects/weapons').glob('*.wiki'))
            for relative in inputs+targets:
                target=root/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(study.ROOT/relative,target)
            with patch.object(weapons,'ROOT',root):
                weapons.generate(check=True)
                shard='wiki/modules/TD2武器图表/Pistol.lua'
                with (root/shard).open('ab') as out:
                    out.write(b'-- stale\n')
                with self.assertRaisesRegex(ValueError,'Stale generated weapon sources: '+shard):
                    weapons.generate(check=True)
                self.assertTrue((root/shard).read_bytes().endswith(b'-- stale\n'))
