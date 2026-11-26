import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from formal_candidate import ROOT, EDITOR, NODE, candidate


class ResourceNamingTests(unittest.TestCase):
    def test_compiled_runtime_fetches_catalog_then_loads_current_page(self):
        runtime=candidate()/'resources/TD2EditorRuntime.js'
        run=subprocess.run([NODE,str(ROOT/'tests/runtime_bootstrap.cjs'),str(runtime)],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
        self.assertEqual(run.returncode,0,run.stderr)

    def test_compiled_runtime_and_entry_share_the_formal_export_and_version(self):
        resources = candidate() / 'resources'
        source = """
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const dir=process.argv[1],manifest=JSON.parse(fs.readFileSync(dir+'/manifest.json','utf8'));
function context(id){const values={wgNamespaceNumber:0,wgAction:'view',wgUserId:id,wgUserGroups:id?['sysop']:[],wgUserName:id?'Admin':null,wgPageName:'5.11_Tactical',wgArticleId:999};return {mw:{config:{get:k=>values[k]}},location:{origin:'https://td2.huijiwiki.com',href:'https://td2.huijiwiki.com/wiki/5.11_Tactical'},URL,console};}
const runtime=context(1);vm.runInNewContext(fs.readFileSync(dir+'/TD2EditorRuntime.js','utf8'),runtime);
assert.equal(runtime.mw.td2EditorRuntime.version,manifest.version);assert.equal(typeof runtime.mw.td2EditorRuntime.open,'function');
const reader=context(0);vm.runInNewContext(fs.readFileSync(dir+'/TD2EditorEntry.js','utf8'),reader);
assert.equal(reader.mw.td2EditorEntryStart,undefined);assert.equal(reader.mw.td2EditorEntryPolicy.forms[0].runtime.title,'Gadget:TD2EditorRuntime.js');
assert.equal(reader.mw.td2EditorEntryPolicy.forms[0].runtime.exportName,'td2EditorRuntime');assert.equal(reader.mw.td2EditorEntryPolicy.forms[0].runtime.expected,manifest.version);
"""
        run = subprocess.run([NODE, '-e', source, str(resources)], capture_output=True, text=True, encoding='utf8')
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_one_gadget_per_role_and_no_runtime_autoload(self):
        output = candidate()
        plan = json.loads((output / 'resource-plan.json').read_text(encoding='utf8'))
        config = json.loads((ROOT / 'publishing/reader-editor-production.json').read_text(encoding='utf8'))
        self.assertEqual(len(plan), len(config['content_ids']) + 4 + len(config['resource_naming']['gadgets']) * 2)
        sources={row['source'] for row in plan}
        for name in ('TD2效果映射','TD2装备属性数据','TD2奇特装备'):
            self.assertIn('wiki/modules/'+name+'.lua',sources)
        scripts, styles = [], []
        for row in plan:
            data = (output / row['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            if row['title'].startswith('Gadget definition:'):
                definition = json.loads(data)
                scripts += definition['module']['scripts']
                styles += definition['module']['styles']
        self.assertEqual(scripts, ['TD2Reader.js', 'TD2EditorEntry.js'])
        self.assertEqual(styles, ['TD2Reader.css'])
        self.assertNotIn('TD2EditorRuntime.js', scripts)

    def test_binding_requires_exact_title_bytes_and_positive_revision(self):
        resources = candidate() / 'resources'
        receipt = dict(pageid=900001, title='零件:TD2EditorRuntime.js', revid=900002,
                       raw=(resources / 'TD2EditorRuntime.js').read_text(encoding='utf8'))
        cases = [({}, True), ({'title': '零件:OtherRuntime.js'}, False),
                 ({'revid': 0}, False), ({'pageid': 0}, False), ({'raw': 'wrong'}, False)]
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as tmp:
            for i, (change, valid) in enumerate(cases):
                record, output = Path(tmp) / 'synthetic.json', Path(tmp) / str(i)
                record.write_text(json.dumps(dict(receipt, **change)), encoding='utf8')
                run = subprocess.run([NODE, str(EDITOR / 'production/build.cjs'), '--bind-entry',
                                      str(resources), str(record), str(output)], capture_output=True, text=True, encoding='utf8')
                self.assertEqual(run.returncode == 0, valid, run.stderr)
                if valid:
                    bound = (output / 'TD2EditorEntry.js').read_text(encoding='utf8')
                    self.assertNotIn('REEDIT_RUNTIME_REVISION', bound)
                    self.assertIn("revision: '900002'", bound)
                    self.assertIn('Gadget:TD2EditorRuntime.js', bound)
                else:
                    self.assertFalse(output.exists())
