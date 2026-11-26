import json
import tempfile
import unittest
from pathlib import Path
from tools.publish.bundle import build, PublishError, verify_bundle
from tools.publish.publisher import ManualPublisher


class CommonResourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def candidate(self, suffix='.css', **changes):
        path = self.root / ('wiki/pages/site/Common' + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'/* common fixture */\n')
        row = dict(id='common', kind='pages', source=path.relative_to(self.root).as_posix(),
                   title='MediaWiki:Common' + suffix, namespace=8, related_entity=None,
                   ownership='manual', change_reason='theme fixture', asset_relationships=[],
                   content_model='css' if suffix == '.css' else 'javascript')
        row.update(changes)
        registry = dict(schema_version=1, mode='MANUAL', target='test',
                        namespace_prefixes={'8':['MediaWiki'], '0':['']}, entries=[row])
        for name, obj in [('registry',registry),('baseline',dict(schema_version=1,target='test',entries=[]))]:
            (self.root/(name+'.json')).write_text(json.dumps(obj),encoding='utf-8')
        return build(self.root,self.root/'registry.json',self.root/'baseline.json',self.root/'dist/review')

    def test_css_manual_export_and_prepare(self):
        m=self.candidate();self.assertEqual(m['entries'][0]['content_model'],'css')
        self.assertEqual(m['entries'][0]['conflicts'],['REMOTE_UNVERIFIED'])
        verify_bundle(self.root/'dist/review')
        self.assertIn('MANUAL',ManualPublisher().prepare(self.root/'dist/review'))

    def test_js_explicit_model(self):
        self.assertEqual(self.candidate('.js')['entries'][0]['content_model'],'javascript')

    def test_no_arbitrary_script_title(self):
        with self.assertRaises(PublishError):self.candidate('.js',title='MediaWiki:Unrelated.js')

    def test_no_wrong_namespace(self):
        with self.assertRaises(PublishError):self.candidate(namespace=0,title='Common.css')

    def test_no_generated_common(self):
        with self.assertRaises(PublishError):self.candidate(ownership='generated',generator='fixture')

    def test_no_wrong_model(self):
        with self.assertRaises(PublishError):self.candidate(content_model='javascript')
