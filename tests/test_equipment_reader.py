from current_identity import entity_id, source_for, material_id, asset_file
import json
import re
import unittest
from pathlib import Path
from tools.equipment.wikitext import WikiSubset
from reader_test_html import nodes

ROOT=Path(__file__).resolve().parents[1]

class EquipmentReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=WikiSubset(ROOT,existing_files=['File:'+p.name for p in (ROOT/'assets').glob('*.png')])

    def render(self,group,title):
        return self.reader.expand(source_for(title).read_text('utf8'),{})

    def test_two_acquisitions_use_own_identity_without_manual_fields(self):
        raw=(ROOT/'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text('utf8')
        before=self.reader.expand(raw,{})
        changed=raw.replace('|资料ID=', '|装备获取说明=NON-GAME-FACT 品牌补充\n|图纸获取说明=NON-GAME-FACT 品牌图纸\n|资料ID=',1)
        rendered=self.reader.expand(changed,{})
        self.assertNotIn('NON-GAME-FACT 品牌补充',rendered)
        self.assertNotIn('NON-GAME-FACT 品牌图纸',rendered)
        for before_card,after_card in zip(nodes(before,'td2-equipment'),nodes(rendered,'td2-equipment')):
            self.assertEqual(before_card.text,after_card.text)
        for purpose in ['acquisition','ordinaryBlueprintSource']:
            result=self.reader.expand('{{#invoke:TD2品牌投影|'+purpose+'|source_subject=unknown}}',{})
            self.assertIn('暂无获取资料',result)
            self.assertNotIn('常规获取',result)

    def test_representative_pages_use_actual_lua_without_errors(self):
        for group,title in [('brands','5.11 Tactical'),('brands','捷克出产自律组织'),('brands','道格拉斯与哈定企业'),('gear-sets','政令进行式'),('gear-sets','核心力量'),('exotic-gear','追悼'),('exotic-gear','投资者'),('exotic-gear','阿科斯塔应急包')]:
            with self.subTest(title=title):
                text=self.render(group,title)
                self.assertNotIn('td2-data-error',text)
                self.assertNotIn('<color',text)
                self.assertNotRegex(text,r'\{\d+\}')
                for mode in ['pve','pvp']:self.assertIn('td2-brand-'+mode,text)
                for section in ['装备属性','制作与获取']:self.assertTrue(section in text,section)
                self.assertEqual(text.count('class="td2-expertise-card"'),1)

    def test_legacy_classifications_do_not_render_as_current_acquisition(self):
        text=self.render('brands','5.11 Tactical')
        sources=[n.text for n in nodes(text,'td2-acquisition-result')]
        self.assertTrue(any('重建贮藏箱' in s for s in sources))
        self.assertTrue(any('掉落' in s and '制作' in s for s in sources))
        self.assertFalse(any('常规获取' in s or '暗区掉落' in s for s in sources))
        self.assertIn('掉落',self.render('exotic-gear','阿科斯塔护膝'))

    def test_brand_numeric_format_and_continuous_layout(self):
        text=self.render('brands','5.11 Tactical')
        region=text.split('<div class="td2-brand-bonuses">')[1].split('<span id="品牌主属性">')[0]
        self.assertEqual(re.findall(r'<strong>([^<]+)</strong>',region),['+12.0%','+100%','+30.0%','+10.0%','+100%','+40.0%'])
        self.assertEqual(region.count('class="td2-brand-effect"'),6)
        self.assertNotRegex(region,r'<h[1-6]|件套加成|\+ 件')

    def test_inline_talent_markup_preserves_only_authored_line_breaks(self):
        inline=self.reader.expand('甲{{TD2文字|色=orange|文=10 秒}}。{{TD2图标|类别=state|键=red}} - 加成',{})
        self.assertNotIn('\n',inline)
        for group,title,breaks,paragraphs in [('exotic-gear','追悼',4,8),('gear-sets','政令进行式',0,14)]:
            with self.subTest(title=title):
                text=self.render(group,title)
                descriptions=re.findall(r'<div class="td2-talent-description">(.*?)</div>',text,re.S)
                self.assertEqual(sum(s.count('<br>') for s in descriptions),breaks)
                self.assertEqual(sum(s.count('<p>') for s in descriptions),paragraphs)
                self.assertTrue(all('<p></p>' not in s for s in descriptions))
                self.assertTrue(all(not re.search(r'<br>[。，、：；]',s) for s in descriptions))

    def test_named_talent_reference_uses_shared_mapping_and_independent_modes(self):
        raw=(ROOT/'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text('utf8')
        text=self.reader.expand(raw,{})
        self.assertNotIn('完美守护者',raw)
        titles=[n.text for n in nodes(text,'td2-talent-copy')];self.assertTrue(any('完美守护者' in t for t in titles))
        pve=next(n for n in nodes(text,'td2-brand-panel') if '完美守护者' in n.text and 'td2-brand-pve' in n.attrs['class'])
        pvp=next(n for n in nodes(text,'td2-brand-panel') if '完美守护者' in n.text and 'td2-brand-pvp' in n.attrs['class'])
        self.assertIn('+25%',pve.text);self.assertIn('+15%',pvp.text)

    def test_gear_effects_keep_activation_counts_unique_anchors_and_slot_links(self):
        text=self.render('gear-sets','政令进行式')
        ids=re.findall(r'id="(td2-gear-[^"]+)"',text)
        self.assertEqual(len(ids),len(set(ids)))
        for anchor in re.findall(r'\[\[#(td2-gear-[^|]+)\|',text):self.assertIn(anchor,ids)
        self.assertEqual([n.text for n in nodes(text,'td2-gear-effect-title')],['2+ 件','3+ 件','4+ 件']*2)
        headings=[n.text for n in nodes(text,'td2-talent-section-title')]
        self.assertEqual(headings.count('背包天赋'),2);self.assertEqual(headings.count('胸甲天赋'),2)

    def test_named_talent_headings_follow_effect_content_once(self):
        for title,count in [('栅状钢铁',2),('5.11 Tactical',1)]:
            text=self.render('brands',title)
            self.assertEqual(len(nodes(text,'td2-talent-section-title')),count)
            for card in nodes(text,'td2-equipment'):
                talents=card.find_all('td2-talent-copy')
                self.assertEqual([n.text for n in card.find_all('td2-talent-section-title')],['天赋'] if talents else [])
                if talents:
                    self.assertEqual(len(talents),2)
                    self.assertEqual(len(card.find_all('td2-talent-icon')),2)
                    self.assertEqual([n.attrs['class'] for n in card.find_all('td2-brand-panel')],['td2-brand-panel td2-brand-pve','td2-brand-panel td2-brand-pvp'])

    def test_named_missing_effects_do_not_render_catalog_or_empty_heading(self):
        card=self.reader.template('品牌装备摘要',{'stable_id':'gear_511_keeper'})
        text=self.reader.lua_boundary.invoke('TD2品牌投影','namedCards',{'cards':card,'effects':''})
        self.assertFalse(nodes(text,'td2-talent-section-title'))
        self.assertFalse(nodes(text,'td2-talent-copy'))
        self.assertNotIn('完美守护者',text)

    def _render_named_fixture(self, mapping):
        reader=WikiSubset(ROOT,sources={'wiki/modules/TD2装备映射.lua':'return '+mapping})
        card=reader.template('品牌装备摘要内容',{'stable_id':'test_named','装备部位':'backpack','装备名称':'NON-GAME-FACT','talent_mode':'none'})
        return reader.lua_boundary.invoke('TD2品牌投影','namedCards',{'cards':card})

    def test_named_core_requires_complete_formal_mapping(self):
        for mapping in [
            '{named={},entities={}}',
            '{named={test_named={["资料ID"]="test_entity"}},entities={}}',
            '{named={test_named={["资料ID"]="test_entity"}},entities={test_entity={rules={}}}}',
            '{named={test_named={["资料ID"]="test_entity"}},entities={test_entity={rules={["named:test_named"]={}}}}}',
        ]:
            with self.subTest(mapping=mapping):
                with self.assertRaisesRegex(Exception,'具名主核心映射缺失：test_named'):
                    self._render_named_fixture(mapping)

    def test_named_core_displays_fixed_random_and_multiple_formal_cores(self):
        for core,random,icons in [
            ('{count=1,selection="fixed",types={"yellow"}}',False,['Yellow']),
            ('{count=1,selection="random",types={"red","blue"}}',True,['Red','Blue']),
            ('{count=3,selection="fixed",types={"red","blue","yellow"}}',False,['Red','Blue','Yellow']),
        ]:
            with self.subTest(core=core):
                mapping='{named={test_named={["资料ID"]="test_entity"}},entities={test_entity={rules={["named:test_named"]={core='+core+'}}}}}'
                text=self._render_named_fixture(mapping)
                self.assertEqual(bool(nodes(text,'td2-major-random')),random)
                for color in icons:
                    self.assertIn('TD2-UI-'+color+'-Icon.png',text)
                self.assertEqual(len(nodes(text,'td2-text-orange')),0 if random else len(icons))

    def test_shared_talent_display_preserves_parameters_without_section_title(self):
        from tools.brand_sets.projection import knowledge_sources
        path='wiki/templates/TD2天赋资料.wiki'
        self.assertEqual((ROOT/path).read_text('utf8'),knowledge_sources()[path])
        text=self.reader.template('TD2天赋资料',{'名称':'NON-GAME-FACT','描述':'<p>甲</p><p>乙</p>','图标内容':'<span>ICON</span>'})
        self.assertEqual(nodes(text,'td2-talent-copy')[0].text,'NON-GAME-FACT甲乙')
        self.assertEqual(nodes(text,'td2-talent-icon')[0].text,'ICON')
        title=nodes(text,'td2-talent-title')[0]
        self.assertEqual(title.tag,'span')
        self.assertEqual(title.text,'NON-GAME-FACT')
        self.assertFalse(nodes(text,'td2-talent-section-title'))
        self.assertFalse(nodes(text,'td2-brand-panel'))
        text=self.reader.template('TD2天赋资料',{'名称':'NON-GAME-FACT'})
        self.assertFalse(nodes(text,'td2-talent-description'))
        self.assertFalse(nodes(text,'td2-talent-icon'))
        self.assertEqual(self.reader.template('TD2天赋资料',{}),'')

    def test_shared_armor_and_slot_order_with_special_core_structure(self):
        text=self.render('gear-sets','核心力量')
        cards=nodes(text.split('<h2>制作与获取</h2>')[0],'td2-equipment-card')
        self.assertEqual(len(cards),6)
        for card,name,armor in zip(cards,['面具','背包','胸甲','手套','枪套','护膝'],['80.3K','130.8K','158.0K','80.3K','111.9K','98.7K']):
            self.assertIn(name,card.text);self.assertIn('基础装甲：'+armor,card.text)
        backpack=cards[1].text
        for core in ['武器伤害','装甲','技能分阶']:self.assertIn(core,backpack)
        self.assertNotIn('随机加成',backpack)

    def test_independent_empty_pvp_does_not_inherit_pve(self):
        raw='{{装备效果|效果ID=x|模式=PvE|件数=4|名称=独立效果|描述=PvE独有}}'
        text=self.reader.template('装备组内容',{'效果资料':self.reader.expand(raw,{})})
        self.assertIn('PvE独有',text);self.assertNotIn('td2-brand-pvp',text)

    def test_local_catalog_preserves_json_arrays_without_embedding_in_runtime(self):
        text=self.reader.expand('{{#invoke:TD2编辑数据|export}}',{})
        import html
        data=json.loads(html.unescape(re.search('data-td2-editor-catalog="([^"]+)"',text)[1]))
        self.assertIsInstance(data['catalog'],list)
        self.assertEqual(set(next(iter(data['options']['equipmentCatalog'].values()))),{'template','title'})
        self.assertNotIn('exoticSnapshot',data)

    def test_unbranded_keeps_six_models_without_brand_effects(self):
        text=self.render('equipment','临时制作')
        self.assertNotIn('<h2>套装加成</h2>',text)
        self.assertNotIn('<h2>具名装备</h2>',text)
        self.assertEqual(len(re.findall('id="gear-',text)),6)
