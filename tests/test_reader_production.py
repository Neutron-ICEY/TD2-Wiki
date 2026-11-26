from tools import identity as identity_catalog
import hashlib
import json
from pathlib import Path
import unittest

from formal_candidate import ROOT, candidate
from tools.brand_sets.dependencies import dependencies
from wiki_subset import WikiSubset


class ProductionReaderTests(unittest.TestCase):
    def test_literal_require_dependencies_include_current_shared_modules(self):
        text="require ('Module:One')\nrequire \"模块:Two\"\nlocal dynamic=require(name)"
        self.assertEqual(dependencies(text),{('module','One'),('module','Two')})
        for name in ['TD2装备组投影','TD2品牌投影']:
            found=dependencies((ROOT/'wiki/modules'/(name+'.lua')).read_text('utf8'))
            self.assertTrue({('module','TD2资料记录'),('module','TD2资料映射')}<=found)
        plan=json.loads((candidate()/'resource-plan.json').read_text('utf8'))
        row=next(r for r in plan if r['source']=='wiki/modules/TD2装备组投影.lua')
        self.assertTrue({'Module:TD2资料记录','Module:TD2资料映射'}<=set(row['dependencies']))

    def test_brand_and_named_blueprint_sources_use_the_shared_body_boundary(self):
        from reader_test_html import nodes
        from tools.equipment.lua import LuaBoundary
        view=WikiSubset(ROOT);view.lua_boundary=LuaBoundary(view)
        view.lua_boundary.lua.eval("require('Module:TD2装备映射')")['acquisition']=view.lua_boundary.lua.table()
        rendered = view.template('品牌套装内容', {
            '套装全称': 'NON-GAME-FACT brand', 'mask图纸': 'NON-GAME-FACT blueprint'})
        self.assertEqual([node.text for node in nodes(rendered, 'td2-acquisition-result')],
                         ['暂无获取资料', '暂无获取资料'])
        headings = nodes(rendered, 'td2-source-heading')
        self.assertEqual([h.tag for h in headings], ['h3', 'h3', 'h3'])
        for heading,title in zip(headings, ('装备图纸', '图纸获取', '装备获取')):
            self.assertRegex(heading.text, r'^\[\[[^|]+\|' + title + r'\]\]$')
        named = WikiSubset(ROOT).template('品牌装备摘要内容', {
            'stable_id': 'non_game_fact', '装备部位': 'mask', '装备名称': 'NON-GAME-FACT named'})
        self.assertEqual([node.text for node in nodes(named, 'td2-acquisition-result')],
                         ['暂无获取资料'])

    def test_formal_page_dependency_closure_is_registered(self):
        registry = json.loads((ROOT / 'publishing/registry.json').read_text(encoding='utf8'))
        sources = {('module' if r['kind'] == 'modules' else 'template', r['title'].split(':', 1)[1]): r
                   for r in registry['entries'] if r['kind'] in ('templates', 'modules')}
        visited = set()
        def visit(text):
            for dep in dependencies(text):
                if dep == ('template', 'Infobox') or dep in visited:
                    continue
                self.assertIn(dep, sources)
                visited.add(dep)
                visit((ROOT / sources[dep]['source']).read_text(encoding='utf8'))
        page = (ROOT / 'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text(encoding='utf8')
        visit(page)
        self.assertGreater(len(visited), 30)
        self.assertTrue(all('Sandbox' not in n for k, n in visited))
        self.assertNotIn('{{品牌装备摘要',page)
        entity=next(e for e in identity_catalog.read_json(ROOT/'data/equipment/records.json')['entities'].values() if e['source']=='wiki/pages/brands/品牌套装-5.11 Tactical.wiki')
        self.assertEqual(sum(len(c['rows']) for key,c in entity['collections'].items() if key.endswith('型号资料')),14)

    def test_formal_reader_preserves_data_and_layout(self):
        acquisition = identity_catalog.read_json(ROOT / 'data/brand-sets/acquisition-methods.json')
        page = (ROOT / 'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text(encoding='utf8')
        rendered = WikiSubset(ROOT, acquisition=acquisition).expand(page, {})
        for name in ('gear_511_keeper', 'gear_511_deathgrips', '完美守护者', '死亡之握', '分享就是关怀。'):
            self.assertIn(name, rendered)
        for heading in ('套装加成', '装备属性', '具名装备', '制作与获取', '分解产物', '专精'):
            self.assertIn(heading, rendered)
        self.assertIn('随机加成', rendered)


    def test_reader_styles_are_shared_and_editor_build_is_reproducible_from_sources(self):
        output = candidate()
        self.assertEqual((output / 'resources/TD2Reader.css').read_bytes(), (ROOT / 'ui/brand-sets/brand-sets.css').read_bytes())
        self.assertNotIn('body.page-', (output / 'resources/TD2Reader.css').read_text(encoding='utf8'))
        manifest = json.loads((output / 'editor/manifest.json').read_text(encoding='utf8'))
        self.assertEqual(manifest['releaseMode'], 'formal')
        self.assertTrue(all('/dist/' not in r['source'] and '/review-' not in r['source'] for r in manifest['inputs']))
        self.assertTrue(all(not Path(r['source']).is_absolute() and '..' not in Path(r['source']).parts
                            and 'local-archive' not in Path(r['source']).parts for r in manifest['inputs']))
        self.assertIn('ui/editor/production/build.cjs', {r['source'] for r in manifest['inputs']})
        self.assertTrue(all(not r['source'].endswith('/mvp/index.html') for r in manifest['inputs']))

    def test_formal_materials_use_the_shared_canonical_row(self):
        materials = list((ROOT / 'wiki/pages/materials').glob('*.wiki'))
        self.assertEqual(len(materials), 12)
        for page in materials:
            text = page.read_text(encoding='utf8')
            self.assertIn('{{TD2材料行|', text)

    def test_editor_build_records_shared_equipment_ui_and_exact_input_hashes(self):
        manifest = json.loads((candidate() / 'editor/manifest.json').read_text(encoding='utf8'))
        inputs = manifest['inputs']
        self.assertEqual(len(inputs), len({row['source'] for row in inputs}))
        self.assertNotIn('data/brand-sets/equipment-ui.json', {row['source'] for row in inputs})
        self.assertIn('ui/editor/src/mapped-domain.js', {row['source'] for row in inputs})
        for row in inputs:
            with self.subTest(source=row['source']):
                self.assertEqual(hashlib.sha256((ROOT / row['source']).read_bytes()).hexdigest(), row['sha256'])
