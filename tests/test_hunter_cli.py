"""离线验证目标约束、选择校验和逐项结果；不启动 Hunter，不读取游戏文件。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.hunter_cli.core import Bridge, image_query, raw_query, read_json, resource_path, validate_targets


class HunterCliTests(unittest.TestCase):
    def test_raw_namespaces_and_sidecar_collisions(self):
        for namespace in ('hunter','rogue'):
            name=namespace+'/game system data/中文.mitem'
            self.assertEqual(resource_path(name,'raw').as_posix(),'raw_files/'+name)
            self.assertEqual(raw_query('中文.mitem',namespace),namespace+'/,中文.mitem')
        for names in (['rogue/../outside'],['rogue/a.mitem','rogue/a.mitem.decompiled']):
            with self.assertRaises(ValueError): validate_targets(names,'raw')
        with self.assertRaises(ValueError): raw_query('')
        with self.assertRaises(ValueError): validate_targets(['rogue/a.mitem'])

    def test_raw_batch_records_binary_and_sidecar_without_image_validation(self):
        scratch=Path(__file__).resolve().parents[1]/'dist'
        with TemporaryDirectory(prefix='hunter-raw-test-',dir=scratch) as directory:
            bridge=Bridge.__new__(Bridge);bridge.session=Path(directory);bridge.hwnd=1
            selected={}
            bridge.set_output=lambda raw:selected.update(raw=raw)
            def select(name,kind):
                if name.endswith('missing.mitem'): raise RuntimeError('TARGET_NOT_FOUND')
                selected['name']=name
            bridge.select_exact=select
            def export(*args):
                p=selected['raw']/resource_path(selected['name'],'raw')
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes(b'\x00\xffnative')
                Path(str(p)+'.decompiled').write_text('definition {}',encoding='utf-8')
            bridge.w=SimpleNamespace(key=Mock(side_effect=export))
            clock=[0]
            def sleep(seconds):clock[0]+=seconds
            with patch('tools.hunter_cli.core.time.sleep',side_effect=sleep),patch('tools.hunter_cli.core.time.monotonic',side_effect=lambda:clock[0]):
                result=bridge.batch(['hunter/missing.mitem','rogue/中文.mitem'],
                    {'path':'test.sdftoc','sha256':'0'*64},timeout=10,kind='raw')
            self.assertEqual((result['success_count'],result['failed_count']),(1,1))
            record=result['exports'][0]
            self.assertEqual([f['role'] for f in record['files']],['raw','decompiled'])
            self.assertFalse(record['definition_semantics_verified'])
            self.assertEqual(record['resource_id'],'UNKNOWN')
            manifest=read_json(Path(result['receipt_path']).parent/'hunter/raw-export-manifest.json')
            self.assertEqual(manifest['exported_file_count'],2)
            self.assertFalse((Path(result['receipt_path']).parent/'hunter/export-manifest.json').exists())

    def test_raw_cancel_and_missing_output(self):
        scratch=Path(__file__).resolve().parents[1]/'dist'
        with TemporaryDirectory(prefix='hunter-raw-test-',dir=scratch) as directory:
            bridge=Bridge.__new__(Bridge);bridge.session=Path(directory)
            with self.assertRaisesRegex(RuntimeError,'RAW_OUTPUT_TIMEOUT_OR_UNSTABLE'):
                bridge.raw_record(bridge.session/'missing','hunter/missing',{},0)
            (bridge.session/'cancel').touch()
            with self.assertRaisesRegex(RuntimeError,'CANCELLED'):
                bridge.raw_record(bridge.session/'missing','hunter/missing',{},float('inf'))

    def test_explicit_targets_preserve_unicode_and_spaces(self):
        name = 'hunter/ui/中文 名称'
        self.assertEqual(validate_targets([name]), [name])
        self.assertEqual(resource_path(name).as_posix(), 'images/hunter/ui/中文 名称.png')

    def test_unsafe_or_ambiguous_targets_rejected(self):
        for names in ([], ['hunter/a'] * 2, ['hunter/a', 'hunter/A'],
                      ['hunter/../outside'], ['C:/outside'], ['hunter/a,b'],
                      ['hunter/a.'], ['hunter/a\\b'], ['hunter/a'] * 21):
            with self.subTest(names=names), self.assertRaises(ValueError):
                validate_targets(names)

    def test_query_restricts_images_without_inventing_metadata(self):
        self.assertEqual(image_query('logo,width:2048'), 'width:>0,hunter/,logo,width:2048')
        with self.assertRaises(ValueError):
            image_query('a,b,c,d,e')

    def test_exact_selection_rejects_near_match(self):
        bridge = Bridge.__new__(Bridge)
        bridge.search = Mock(return_value={'resources': [{'name': 'hunter/ab'}], 'end_observed': True})
        bridge.w = SimpleNamespace(key=Mock())
        bridge.hwnd = 1
        with self.assertRaisesRegex(RuntimeError, 'TARGET_NOT_FOUND'):
            bridge.select_exact('hunter/a')
        bridge.w.key.assert_not_called()

    def test_exact_selection_requires_final_clipboard_match(self):
        bridge = Bridge.__new__(Bridge)
        bridge.search = Mock(return_value={'resources': [{'name': 'hunter/a'}], 'end_observed': True})
        bridge.copied_selection = Mock(return_value='hunter/b')
        with self.assertRaisesRegex(RuntimeError, 'EXACT_SELECTION_READBACK_FAILED'):
            bridge.select_exact('hunter/a')

    def run_batch(self, first_error=None, cancel=False, cancel_during_selection=False):
        from PIL import Image
        scratch = Path(__file__).resolve().parents[1] / 'dist'
        scratch.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix='hunter-cli-test-', dir=scratch) as directory:
            bridge = Bridge.__new__(Bridge)
            bridge.session = Path(directory)
            bridge.hwnd = 1
            selected = {}

            def set_output(raw):
                selected['raw'] = raw

            def select(name):
                if name == 'hunter/missing' and first_error:
                    raise RuntimeError(first_error)
                selected['name'] = name
                if cancel_during_selection:
                    (bridge.session / 'cancel').touch()

            def export(*args):
                path = selected['raw'] / resource_path(selected['name'])
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new('RGBA', (2, 3), (10, 20, 30, 255)).save(path)

            bridge.set_output = set_output
            bridge.select_exact = select
            bridge.w = SimpleNamespace(key=Mock(side_effect=export))
            if cancel:
                (bridge.session / 'cancel').touch()
            with patch('tools.hunter_cli.core.time.sleep'):
                result = bridge.batch(['hunter/missing', 'hunter/valid'],
                                      {'path': 'synthetic.sdftoc', 'sha256': '0' * 64}, timeout=1)
            persisted = read_json(result['receipt_path'])
            manifest = read_json(Path(result['receipt_path']).parent / 'hunter/export-manifest.json')
            return result, persisted, manifest, bridge.w.key.call_count

    def test_missing_target_preserves_later_valid_export_and_provenance(self):
        result, persisted, manifest, calls = self.run_batch('TARGET_NOT_FOUND')
        self.assertEqual((result['success_count'], result['failed_count'], calls), (1, 1, 1))
        self.assertEqual(persisted['status'], 'PARTIAL_OR_FAILED')
        self.assertEqual(manifest['exported_file_count'], 1)
        self.assertEqual(result['exports'][0]['resource_name'], 'hunter/valid')
        self.assertEqual(result['exports'][0]['resource_id'], 'UNKNOWN')

    def test_unknown_ui_failure_stops_further_exports(self):
        result, _, _, calls = self.run_batch('FOCUS_LOST')
        self.assertEqual((result['success_count'], result['failed_count'], result['not_attempted_count'], calls),
                         (0, 1, 1, 0))

    def test_cancel_does_not_send_export(self):
        result, _, _, calls = self.run_batch(cancel=True)
        self.assertEqual(calls, 0)
        self.assertEqual(result['items'][0]['error'], 'CANCELLED')

    def test_cancel_during_selection_does_not_send_export(self):
        result, _, _, calls = self.run_batch(cancel_during_selection=True)
        self.assertEqual(calls, 0)
        self.assertEqual(result['items'][0]['error'], 'CANCELLED')


if __name__ == '__main__':
    unittest.main()
