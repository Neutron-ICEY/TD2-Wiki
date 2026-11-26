from current_identity import entity_id, source_for, material_id, asset_file
from tools import identity as identity_catalog
import unittest
import re
from pathlib import Path
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class GearSetReaderTests(unittest.TestCase):
    def view(self):
        from tools.equipment.lua import LuaBoundary
        view=WikiSubset(ROOT);view.lua_boundary=LuaBoundary(view)
        view.lua_boundary.lua.eval("require('Module:TD2装备映射')")['acquisition']=view.lua_boundary.lua.table()
        return view

    def test_source_headings_remain_outside_toc_and_share_body_containers(self):
        from reader_test_html import nodes
        rendered = self.view().template('装备组内容', {
            'mask图纸': 'NON-GAME-FACT blueprint'})
        headings = nodes(rendered, 'td2-source-heading')
        self.assertEqual([node.tag for node in headings], ['div'] * 3)
        self.assertEqual([node.text.split('|')[-1].rstrip(']') for node in headings],
                         ['装备图纸', '图纸获取', '装备获取'])
        self.assertNotIn('td2-text-gold', ''.join(node.attrs['class'] for node in headings))
        self.assertEqual([node.text for node in nodes(rendered, 'td2-acquisition-result')],
                         ['暂无获取资料', '暂无获取资料'])

    def test_blueprint_names_do_not_imply_their_acquisition_source(self):
        from reader_test_html import nodes
        view=self.view()
        for fields,count in [({},6),({'mask图纸':'原生制作目标'},5),({'mask图纸':'无制作图纸'},6)]:
            rendered=view.template('装备组内容',fields)
            self.assertEqual(rendered.count('class="td2-blueprint-none"'),count)
            self.assertEqual([n.text for n in nodes(rendered,'td2-acquisition-result')],['暂无获取资料','暂无获取资料'])

    def test_ongoing_directive_dismantle_combines_verified_amounts_and_native_rules(self):
        out = self.view().template('装备组内容', {'GearSet ID':'set:4cdce5b25bc1f2cc0002efead01ec184','装备组名称':'政令进行式','装备组分解材料':'政令进行式材料'})
        self.assertEqual(out.count('<ul class="td2-materials">'), 6)
        self.assertEqual(out.count('class="td2-material-quantity">'), 48)
        self.assertNotIn('数量待核实', out)
        self.assertEqual(out.count('class="td2-material-quantity">23<'), 6)
        self.assertEqual(out.count('class="td2-material-quantity">4<'), 18)
        self.assertEqual(out.count('class="td2-material-quantity">1<'), 12)
        self.assertEqual(out.count('class="td2-material-quantity">0 / 10<'), 12)
        self.assertEqual(out.count('class="td2-material-probability">[20%]'), 6)
        self.assertEqual(out.count('class="td2-material-probability">[10%]'), 6)
        for material in ('陶瓷碎片', '聚碳酸酯', '碳纤维', '电子元件', '钛合金'):
            self.assertIn(material, out)
        for slot in ('面具', '背包', '胸甲', '手套', '枪套', '护膝'):
            self.assertIn(slot + '织物', out)
        for incorrect in ('23 / 46', '0 / 8'):
            self.assertNotIn(incorrect, out)
        for key in ('unknown', ''):
            result = self.view().template('TD2分解规则', {'1':'mask', '装备组':key or 'unregistered'})
            self.assertNotIn('织物', result)

    def test_ongoing_directive_logo_and_talent_images(self):
        import json
        data = identity_catalog.read_json(ROOT / 'data/gear-sets/sets.json')['sets'][0]
        files = ['File:' + data['logo']['wiki_file']] + ['File:' + icon['wiki_file'] for icon in data['talent_icons'].values()]
        view = WikiSubset(ROOT, existing_files=files)
        logo = view.template('品牌套装信息框', {'套装全称':'政令进行式','图标品牌':entity_id('政令进行式'),'品质':'gear_set'})
        self.assertIn('td2-logo-art', logo)
        self.assertIn('File:' + data['logo']['wiki_file'], logo)
        for key, icon in data['talent_icons'].items():
            self.assertIn('File:' + icon['wiki_file'], view.template('TD2图标', {'类别':'talent','键':key}))


    def test_shared_heading_link_targets_and_plain_blueprint_names(self):
        registry = {row['id']: row for row in identity_catalog.registry(ROOT)}
        out = self.view().template('装备组内容', {'mask图纸':'既有图纸名'})
        self.assertIn('[[指南-制作|装备图纸]]', out)
        self.assertIn(f"[[{registry['crafting-guide']['title']}|图纸获取]]", out)
        self.assertIn(f"[[{registry['loot-guide']['title']}|装备获取]]", out)
        self.assertNotIn('[[既有图纸名', out)
        self.assertNotIn('[[面具图纸', out)
        self.assertIn('<h2>制作与获取</h2>', out)

    def test_shared_optional_icon_distinguishes_missing_mapping_and_missing_file(self):
        from tools.brand_sets.icons import resolver_source
        sources={'wiki/templates/TD2图标.wiki':resolver_source({'talent/mapped':{'wiki_file':'Mapped.png','confirmed_on_wiki':False,'local_asset':{'source':'fixture'}},'talent/empty':{'wiki_file':'','confirmed_on_wiki':False}})}
        args={'类别':'talent','用途':'optional'}
        missing=WikiSubset(ROOT,sources=sources)
        self.assertEqual(missing.template('TD2图标',{**args,'键':'unknown'}).strip(),'')
        self.assertEqual(missing.template('TD2图标',{**args,'键':'empty'}).strip(),'')
        self.assertIn('[[File:Mapped.png|',missing.template('TD2图标',{**args,'键':'mapped'}))
        present=WikiSubset(ROOT,sources=sources,existing_files=['File:Mapped.png'])
        self.assertIn('File:Mapped.png',present.template('TD2图标',{**args,'键':'mapped'}))
        self.assertIn('td2-icon-placeholder',missing.template('TD2图标',{'类别':'talent','键':'unknown'}))

    def test_shared_infobox_and_independent_blueprint_acquisition(self):
        view = self.view()
        out = view.template('装备组内容', {'装备组名称':'未映射实体', '英文原名':'Sample', 'mask图纸':'图纸'})
        self.assertIn('td2-brand-infobox-frame', out)
        self.assertIn('td2-quality-gear_set', out)
        self.assertIn('data-icon-key="equipment_slot/mask"', out)
        self.assertIn('|图纸获取]]', out)
        from reader_test_html import nodes
        self.assertEqual([node.text for node in nodes(out,'td2-acquisition-result')],['暂无获取资料','暂无获取资料'])
        self.assertNotIn('td2-equipment-heading-card', out)
        self.assertEqual(out.count('<h2>套装加成</h2>'), 1)
        brand = view.template('品牌套装信息框', {'套装全称':'品牌'})
        self.assertIn('equipment_slot/backpack', brand)
        self.assertIn('顶级', brand)

    def test_shared_material_without_brand_defaults(self):
        out = self.view().template('装备组内容', {'装备组分解材料':'陶瓷碎片','分解规则':'独立规则'})
        self.assertIn('td2-material-row', out)
        self.assertIn('陶瓷碎片', out)
        self.assertNotIn('独立规则', out)
        self.assertNotIn('23 / 46', out)
        self.assertNotIn('数量待核实', out)


if __name__ == '__main__':
    unittest.main()
