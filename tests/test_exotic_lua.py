from tools import identity as identity_catalog
import json
import copy
import re
from pathlib import Path
import unittest
from exotic_lua_support import ExoticLuaReader, ROOT, equipment_snapshot
from tools.equipment_attributes.catalog import load as load_ordinary
from tools.brand_sets.fixed_minor import resolve
from tools.equipment.native import richtext
def render(text): return ExoticLuaReader().expand(richtext(text),{}).strip()
from reader_test_html import nodes


class ExoticLuaTests(unittest.TestCase):
    def equipment(self,name):
        page = (ROOT / 'tests/fixtures/exotic-gear' / (name + '.wiki')).read_text('utf8')
        key = re.search(r'^\|资料ID=(exotic:[a-f0-9]{32})$', page, re.MULTILINE)[1]
        return key,copy.deepcopy(equipment_snapshot()['equipment'][key])

    def read(self,name):
        return ExoticLuaReader().expand((ROOT/'tests/fixtures/exotic-gear'/(name+'.wiki')).read_text(encoding='utf8'),{})

    def test_actual_lua_renders_all_four_samples(self):
        for name in ('coyote','acosta','memento','investor'):
            with self.subTest(name=name):
                html=self.read(name)
                self.assertIn('data-equipment-version=',html)
                self.assertNotIn('td2-data-error',html)
                self.assertIn('td2-quality-exotic',html)
                self.assertIn('td2-attribute-grid',html)
                self.assertIn('td2-brand-pve',html)
                self.assertIn('td2-brand-pvp',html)
                self.assertNotIn('<color',html)
                self.assertNotIn('{0}',html)
                self.assertNotIn('最高 ',html)
                self.assertNotIn('数值待核实',html)
                self.assertEqual(html.count('role="navigation" aria-label="装备导航"'),1)
                self.assertGreater(html.index('role="navigation"'),html.index('<h2>制作与获取</h2>'))

    def test_shared_preview_preserves_brand_heading_levels(self):
        from tools.equipment.preview import render as preview_render
        raw=(ROOT/'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text(encoding='utf8')
        html=preview_render(raw,ROOT/'tests/fixtures')
        self.assertIn('<h2>制作与获取</h2>',html)
        for title in ('装备图纸','图纸获取','装备获取'):
            self.assertRegex(html,r'<h3[^>]*>\s*<a[^>]*>'+title+r'</a>\s*</h3>')
        self.assertNotRegex(html,r'<h2[^>]*>\s*=')

    def test_preview_definition_lists_preserve_block_boundaries(self):
        from tools.equipment.preview import render_definition_lists
        raw=';Title: unchanged\n:Definition\n<div>body; literal</div>\n;Next\n<p>outside</p>'
        self.assertEqual(render_definition_lists(raw),'<dl><dt>Title: unchanged</dt><dd>Definition</dd></dl>\n<div>body; literal</div>\n<dl><dt>Next</dt></dl>\n<p>outside</p>')

    def test_preview_named_acquisition_titles_are_card_subheadings(self):
        from tools.equipment.preview import render as preview_render
        raw=(ROOT/'wiki/pages/brands/品牌套装-道格拉斯与哈定企业.wiki').read_text(encoding='utf8')
        result=preview_render(raw,ROOT/'tests/fixtures')
        headings = [node for node in nodes(result, 'td2-source-heading') if node.attrs.get('aria-level') == '4']
        self.assertEqual({node.text for node in headings}, {'图纸获取', '装备获取'})
        self.assertTrue(all(node.attrs.get('role') == 'heading' for node in headings))
        self.assertNotRegex(result,r'^;.*(?:图纸|获取)',re.M)

    def test_blueprint_bodies_share_layout_without_merging_purposes(self):
        raw=(ROOT/'tests/fixtures/exotic-gear/coyote.wiki').read_text(encoding='utf8')
        empty_html=ExoticLuaReader().fixed(raw,{'制作图纸':'','重新配置图纸':''})
        self.assertEqual([node.text for node in nodes(empty_html,'td2-blueprint-none')],['无制作图纸','无重新配置图纸'])
        self.assertEqual(len(nodes(empty_html,'td2-acquisition-result')),2)
        self.assertIn('图纸获取',empty_html)
        catalog=equipment_snapshot()
        target=re.search(r'\|资料ID=([^\n]+)',raw)[1].strip()
        references={row['purpose']:row for row in catalog['blueprints'] if row['target_id']==target}
        fields='|制作图纸='+references['craft']['id']+'\n|重新配置图纸='+references['reconfigure']['id']+'\n'
        rendered=ExoticLuaReader().fixed(raw,{key:row['id'] for key,row in [('制作图纸',references['craft']),('重新配置图纸',references['reconfigure'])]})
        inventory,sources=nodes(rendered,'td2-ordinary-blueprints')
        self.assertNotIn('td2-blueprint-sources',inventory.attrs['class'].split())
        self.assertIn('td2-blueprint-sources',sources.attrs['class'].split())
        for group in (inventory,sources):
            self.assertEqual([n.text for n in group.children if getattr(n,'tag','')=='dt'],['制作图纸','重新配置图纸'])
        bodies=[n for n in inventory.children if getattr(n,'tag','')=='dd']
        self.assertEqual([len(node.find_all('td2-blueprints')) for node in bodies],[1,1])
        self.assertIn(references['craft']['name'],bodies[0].text)
        self.assertIn(references['reconfigure']['name'],bodies[1].text)
        self.assertNotIn(references['reconfigure']['name'],bodies[0].text)

    def test_native_structures_and_modes(self):
        self.assertEqual(self.read('memento').count('主属性：</span>'),1)
        acosta=self.read('acosta')
        talents=acosta.split('<h3 class="td2-talent-section-title">天赋</h3>')[1].split('<h2>制作与获取</h2>')[0]
        self.assertEqual(len(nodes(talents,'td2-talent-detail')),4)
        self.assertEqual(len(nodes(acosta,'td2-expertise-card')),1)
        investor=self.read('investor')
        self.assertEqual(investor.count('次属性：</span>'),3)
        self.assertIn('无插件槽位',investor)
        attributes=investor.split('<h2>装备属性</h2>')[1].split('<h3 class="td2-talent-section-title">')[0]
        self.assertEqual(attributes.count('随机加成'),4)
        self.assertNotIn(' / ',attributes)
        self.assertNotIn('暴击伤害',attributes)
        coyote=self.read('coyote')
        pve,pvp=coyote.split('td2-brand-pvp',1)
        self.assertIn('+25%',pve);self.assertIn('+18%',pvp)
        acosta=self.read('acosta');pve,pvp=acosta.split('td2-brand-pvp',1)
        self.assertIn('超载',pve);self.assertNotIn('超载',pvp)

    def test_generic_minor_pool_choices_keep_random_slots_and_modes(self):
        raw=(ROOT/'tests/fixtures/exotic-gear/investor.wiki').read_text(encoding='utf8')
        for pool in ('pool_minor','pool_minor_offense','pool_minor_defense','pool_minor_utility'):
            with self.subTest(pool=pool):
                key,item=self.equipment('investor')
                for row in item['slots']:
                    if row.get('候选池')=='pool_investor_minor': row['候选池']=pool
                html=ExoticLuaReader(equipment_patch={'equipment':{key:item}}).expand(raw,{})
                self.assertNotIn('td2-data-error',html)
                self.assertEqual(html.count('次属性：</span>'),3)
                self.assertIn('td2-brand-pve',html)
                self.assertIn('td2-brand-pvp',html)

    def test_shared_talents_follow_attributes_without_duplicate_slot(self):
        for name in ('coyote','acosta','memento','investor'):
            with self.subTest(name=name):
                html=self.read(name)
                self.assertEqual(len(nodes(html,'td2-brand-infobox-frame')),1)
                self.assertEqual(len(nodes(html,'td2-brand-name-en')),1)
                self.assertIn('奇特',nodes(html,'td2-brand-quality')[0].text)
                heading='<h3 class="td2-talent-section-title">天赋</h3>'
                self.assertEqual(html.count(heading),1)
                self.assertLess(html.index('<h2>装备属性</h2>'),html.index(heading))
                self.assertLess(html.index(heading),html.index('<h2>制作与获取</h2>'))
                self.assertNotIn('<h2>天赋</h2>',html)
                self.assertNotIn('天赋位：</span>',html)
                self.assertNotIn('td2-gear-talent-links',html)
                self.assertEqual(html.count('主属性：</span>'),1)
                summary=html.split('<h2>装备属性</h2>')[1].split(heading)[0]
                self.assertNotIn('td2-talent-description',summary)
                talents=html.split(heading)[1].split('<h2>制作与获取</h2>')[0]
                self.assertEqual(len(nodes(talents,'td2-talent-detail')),4 if name=='acosta' else 2)
                self.assertEqual(len(nodes(talents,'td2-talent-icon')),4 if name=='acosta' else 2)
        acosta=self.read('acosta')
        for group in nodes(acosta,'td2-brand-bonuses')[0].find_all('td2-brand-panel'):
            self.assertIn('一个在手',group.text)
            self.assertIn('两个在包',group.text)
        self.assertIn('1.0',self.read('memento'))

    def test_talent_inline_cores_reuse_confirmed_state_icons(self):
        for name in ('offense','defense','utility'):
            self.assertIn('data-icon-key="state/',render('<img src="hunter/baked/ui/loose_images/ui_player_'+name+'.dds">'))
        self.assertNotIn('data-icon-key="core_major/',self.read('memento'))

    def test_talent_blues_retain_distinct_native_tokens(self):
        rendered=render('<color name="blue">蓝</color>、<color name="light_blue">蓝色</color>')
        self.assertEqual([n.text for n in nodes(rendered,'td2-text-blue')],['蓝'])
        self.assertEqual([n.text for n in nodes(rendered,'td2-text-light_blue')],['蓝色'])
        investor=self.read('investor')
        self.assertEqual([n.text for n in nodes(investor,'td2-text-light_blue')],['蓝色','蓝色'])

    def test_page_talent_paragraphs_use_shared_description_markup(self):
        for name in ('coyote','acosta','memento','investor'):
            descriptions=nodes(self.read(name),'td2-talent-description')
            self.assertTrue(descriptions)
            self.assertTrue(all(n.find_all('td2-text-orange') or n.text for n in descriptions))
            self.assertTrue(all(any(getattr(c,'tag','')=='p' for c in n.children) for n in descriptions))

    def test_talent_logos_reuse_registered_files_and_acosta_remains_distinct(self):
        talents=identity_catalog.read_json(ROOT/'data/exotic-gear/talents.json')['talents']
        files=['File:'+t['icon']['wiki_file'] for t in talents if t.get('icon')]
        view=ExoticLuaReader(existing_files=files)
        for t in talents:
            rendered=view.template('TD2图标',{'类别':'talent','键':t['id'],'用途':'optional'})
            if t.get('icon'):
                self.assertIn('File:'+t['icon']['wiki_file'],rendered)
            else:
                self.assertNotIn('[[File:',rendered)
        acosta=[t for t in talents if t['native_uid'] in ('0B88A6BC5DDD22960033EFC284CCB7F7','0B88A6BC5DDD2159002E9A26AB520070')]
        self.assertEqual(len({t['icon']['wiki_file'] for t in acosta}),2)
        unobserved=ExoticLuaReader()
        for item in acosta:
            self.assertTrue(item['icon']['local_available'])
            self.assertIn('[[File:'+item['icon']['wiki_file']+'|',
                          unobserved.template('TD2图标',{'类别':'talent','键':item['id']}))

    def test_unknown_rule_and_slot_capacity_do_not_silently_render(self):
        raw=(ROOT/'tests/fixtures/exotic-gear/coyote.wiki').read_text(encoding='utf8')
        for fault in ('rule','identity','count'):
            key,item=self.equipment('coyote')
            if fault=='rule':item['slots'][1]['属性规则']='unknown'
            elif fault=='identity':item['slots'][1]['槽位ID']=item['slots'][0]['槽位ID']
            else:item['fields']['插件槽数']='bad'
            self.assertIn('td2-data-error',ExoticLuaReader(equipment_patch={'equipment':{key:item}}).expand(raw,{}))

    def test_all_maintained_exotic_armor_renders_with_real_lua(self):
        reader=ExoticLuaReader()
        entries=identity_catalog.registry(ROOT)
        assets={r['id']:r for r in entries if r['kind']=='assets'}
        entities=identity_catalog.read_json(ROOT/'data/equipment/records.json')['entities']
        rows=[r for r in entries if r['kind']=='pages' and (r.get('related_entity') or '').startswith('exotic:')]
        self.assertEqual(len(rows),36)
        for row in rows:
            with self.subTest(title=row['title']):
                html=reader.expand((ROOT/row['source']).read_text(encoding='utf8'),{})
                self.assertNotIn('td2-data-error',html)
                self.assertNotIn('{0}',html)
                self.assertNotIn('<color',html)
                self.assertIn('td2-brand-pve',html)
                self.assertIn('td2-brand-pvp',html)
                entity=entities[row['related_entity']]
                article, = nodes(html,'td2-exotic-gear')
                attributes, = article.find_all('td2-equipment-attributes')
                self.assertIn(attributes,article.children)
                self.assertEqual(len(attributes.find_all('td2-attribute-grid')),1)
                flavors=article.find_all('td2-equipment-flavor')
                self.assertEqual(len(flavors),int(bool(entity['fields'].get('简介'))))
                if flavors:
                    self.assertLess(article.children.index(flavors[0]),article.children.index(attributes))
                self.assertIn(identity_catalog.display_name(entity),html)
                asset=assets[entity['visuals']['inventory']['asset_ref']]
                self.assertEqual(asset['related_entity'],row['related_entity'])
                self.assertIn(asset['id'],row['asset_relationships'])
                card, = nodes(html,'td2-exotic-infobox')
                art, = card.find_all('td2-brand-logo')
                self.assertIn('[['+asset['title']+'|',''.join(art.children))

    def test_shared_named_reader_retains_special_values(self):
        reader=ExoticLuaReader()
        html=reader.template('品牌次属性行',{'数量':'2','固定次属性':'ordinary_minor_critical_hit_chance;ordinary_minor_critical_hit_damage'})
        self.assertIn('6%',html);self.assertIn('12%',html);self.assertNotIn('随机加成',html)
        special=reader.template('品牌次属性行',{'数量':'2','固定次属性':'fixed_minor_punch_drunk_headshot_damage'})
        self.assertIn('20.0%',special);self.assertIn('随机加成',special)
        data=identity_catalog.read_json(ROOT/'data/brand-sets/fixed-minor-presets.json')
        minor=identity_catalog.read_json(ROOT/'data/brand-sets/minor-attributes.json')
        self.assertEqual(resolve(data,minor,'ordinary_minor_headshot_damage',load_ordinary(ROOT))['value'],'10')
        self.assertEqual(resolve(data,minor,'fixed_minor_punch_drunk_headshot_damage')['value'],'20.0')

    def test_native_markup_is_allowlisted(self):
        self.assertIn('td2-text-orange',render('<color name="orange">+25%</color>'))
        for raw in ('<script>alert(1)</script>','<img src="https://unknown/a">','<color name="unknown">x</color>'):
            with self.assertRaises(ValueError):render(raw)

    def test_native_color_typography_and_unbalanced_colors_preserve_words(self):
        self.assertEqual(render('<color name=”orange”>45%</color>'), '<span class="td2-text-orange">45%</span>')
        self.assertEqual(render('A</color>B<color name="orange">C'), 'AB<span class="td2-text-orange">C</span>')

    def test_browser_saved_named_candidate_reaches_parent_reader(self):
        raw=(ROOT/'wiki/pages/brands/品牌套装-捷克出产自律组织.wiki').read_text(encoding='utf8')
        html=ExoticLuaReader().expand(raw,{})
        section=html.split('id="named-gear_',2)[-1]
        self.assertIn('6%',section)
        self.assertIn('12%',section)
        self.assertNotIn('最高 ',section)
        self.assertIn('迷惑',section)

    def test_base_armor_and_each_core_use_existing_templates(self):
        reader=ExoticLuaReader()
        for name,slot in [('memento','backpack'),('acosta','backpack'),('coyote','mask'),('investor','mask')]:
            armor=reader.template('TD2普通装备规则',{'1':'armor','部位':slot})
            self.assertIn('<p class="td2-base-armor">基础装甲：'+armor+'</p>',self.read(name))
        memento=self.read('memento')
        for key in ('red','blue','yellow'):
            self.assertIn(reader.template('TD2主属性显示',{'1':key}),memento)
        self.assertIn('170,000',memento)
        self.assertEqual(memento.count('class="td2-major-option"'),3)
        coyote=self.read('coyote')
        for key in ('ordinary_minor_critical_hit_chance','ordinary_minor_critical_hit_damage'):
            self.assertIn(reader.template('TD2固定词条片段',{'1':key}),coyote)

    def test_core_group_reuses_slot_row_and_random_brand_projection(self):
        reader=ExoticLuaReader()
        values='<br>'.join(reader.template('TD2主属性显示',{'1':key}) for key in ('red','blue','yellow'))
        group=reader.template('TD2装备槽行',{'数量':'1','标签':'主属性','图标':'major_attribute','内容':'<span class="td2-major-value">'+values+'</span>'})
        self.assertIn(group,self.read('memento'))
        for name in ('memento','coyote','acosta','investor'):
            self.assertEqual(self.read(name).count('主属性：</span>'),1)
        random=reader.template('TD2主属性列表',{'1':'red;blue;yellow'})
        self.assertIn(random,self.read('investor'))
        self.assertIn('state/red',random)
        self.assertIn('state/blue',random)
        self.assertIn('state/yellow',random)
        self.assertNotIn('state/random',random)
        self.assertNotIn('15%',random)

    def test_unsupported_percentile_does_not_claim_a_maximum(self):
        raw=(ROOT/'tests/fixtures/exotic-gear/memento.wiki').read_text(encoding='utf8')
        key,item=self.equipment('memento')
        for row in item['slots']:row['预设百分位']='50'
        html=ExoticLuaReader(equipment_patch={'equipment':{key:item}}).expand(raw,{})
        self.assertNotIn('td2-data-error',html)
        self.assertNotIn('170,000',html)
        self.assertNotIn('数值待核实',html)

    def test_percentile_contract_matches_editor_cases(self):
        raw=(ROOT/'tests/fixtures/exotic-gear/memento.wiki').read_text(encoding='utf8')
        cases=json.loads((ROOT/'tests/fixtures/exotic-percentiles.json').read_text(encoding='utf8'))
        reader=ExoticLuaReader()
        for case in cases:
            with self.subTest(value=case['value']):
                key,item=self.equipment('memento')
                for row in item['slots']:row['预设百分位']=case['value']
                html=ExoticLuaReader(equipment_patch={'equipment':{key:item}}).expand(raw,{})
                self.assertEqual(case['valid'],'td2-data-error' not in html)
                if case['valid']:
                    self.assertEqual(1,html.count('主属性：</span>'))

    def blueprint_reader(self):
        data=json.loads((ROOT/'tests/fixtures/exotic-blueprints.json').read_text(encoding='utf8'))
        return ExoticLuaReader(equipment_patch={k:data[k] for k in ('blueprints','blueprint_sources')}),data

    def blueprint_render(self,reader,craft=None,reconfigure=None):
        raw=(ROOT/'tests/fixtures/exotic-gear/coyote.wiki').read_text(encoding='utf8')
        return reader.fixed(raw,{'制作图纸':craft or '', '重新配置图纸':reconfigure or ''})

    def test_blueprints_empty_and_reconfigure_are_independent(self):
        reader,data=self.blueprint_reader();reconfigure=data['blueprints'][2]['id']
        for value in (None,''):
            html=self.blueprint_render(reader,value,reconfigure)
            section=html.split('<h2>制作与获取</h2>')[1]
            self.assertIn('无制作图纸',section)
            self.assertIn('NON-GAME-FACT 重新配置',section)
            self.assertEqual(section.count('data-icon-key="state/craft"'),1)
            self.assertNotIn('无重新配置图纸',section)
        for name in ('coyote','acosta','memento','investor'):
            html=self.read(name)
            self.assertNotIn('td2-data-error',html)
            self.assertTrue(nodes(html,'td2-blueprints') or nodes(html,'td2-blueprint-none'))

    def test_blueprint_lists_keep_order_and_identity(self):
        reader,data=self.blueprint_reader();a,b,c=[x['id'] for x in data['blueprints']]
        for ids in (a,b+';'+a):
            html=self.blueprint_render(reader,ids,c)
            lists=nodes(html,'td2-blueprints');self.assertEqual(len(lists),2)
            items=[x for x in lists[0].children if getattr(x,'tag','')=='li']
            self.assertEqual(len(items),len(ids.split(';')))
            self.assertIn('图纸甲; 原文',lists[0].text)
            self.assertNotIn('来源甲',lists[0].text)
            self.assertNotIn('原生提示不显示',html)
            self.assertEqual(html.count('data-icon-key="state/craft"'),len(items)+1)
            if ';' in ids:self.assertLess(lists[0].text.index('图纸乙'),lists[0].text.index('图纸甲'))
        data['blueprints'][1]['name']=data['blueprints'][0]['name']
        reader=ExoticLuaReader(equipment_patch={k:data[k] for k in ('blueprints','blueprint_sources')})
        html=self.blueprint_render(reader,a+';'+b)
        self.assertEqual(nodes(html,'td2-blueprints')[0].text.count('NON-GAME-FACT 图纸甲; 原文'),2)

    def test_blueprint_invalid_references_do_not_become_empty_defaults(self):
        reader,data=self.blueprint_reader();a,b,c=[x['id'] for x in data['blueprints']]
        for value in (a+';'+a,a+';',a+';;'+b,'unknown',c,' '+a+'; '+b):
            html=self.blueprint_render(reader,value)
            self.assertIn('td2-data-error',html)
            self.assertNotIn('无制作图纸',html)
        data['blueprints'][0]['target_id']='exotic:'+'0'*32
        reader=ExoticLuaReader(equipment_patch={k:data[k] for k in ('blueprints','blueprint_sources')})
        self.assertIn('td2-data-error',self.blueprint_render(reader,a))

    def test_multiple_reconfiguration_and_multiple_sources_keep_order(self):
        _,data=self.blueprint_reader()
        a,b,c=[x['id'] for x in data['blueprints']]
        d='blueprint:'+'d'*32
        data['blueprints'].append({**data['blueprints'][2],'id':d,'name':'NON-GAME-FACT 重新配置乙'})
        data['blueprints'][0]['source_refs']=[x['id'] for x in data['blueprint_sources']]
        reader=ExoticLuaReader(equipment_patch={k:data[k] for k in ('blueprints','blueprint_sources')})
        html=self.blueprint_render(reader,a,d+';'+c)
        lists=nodes(html,'td2-blueprints')
        self.assertEqual(len([x for x in lists[1].children if getattr(x,'tag','')=='li']),2)
        self.assertLess(lists[1].text.index('重新配置乙'),lists[1].text.rindex('重新配置'))
        self.assertEqual(html.count('data-icon-key="state/craft"'),3)
        self.assertNotIn('来源甲',lists[0].text)
        self.assertNotIn('原生提示不显示',html)
        self.assertIn('td2-data-error',self.blueprint_render(reader,a,c+';'+c))

    def test_s3_unknown_ordinary_maximum_uses_name_without_changing_special_values(self):
        from unittest.mock import patch
        from tools.brand_sets.build import generate
        ordinary=load_ordinary(ROOT)
        for rule in ordinary['rules']:
            if rule['id'] in ('ordinary_minor_health','ordinary_minor_armor_regen_flat'):
                rule['display_max']=None
        with patch('tools.brand_sets.build.load_ordinary',return_value=ordinary), patch('tools.generation.apply',side_effect=lambda batch,check=False:{relative:data.decode('utf8') for relative,_,data,_ in batch}):
            sources=generate(ROOT)
        reader=ExoticLuaReader(sources=sources)
        html=reader.template('品牌次属性行',{'数量':'2','固定次属性':'ordinary_minor_health;ordinary_minor_armor_regen_flat'})
        values=[n.text for n in nodes(html,'td2-row-value')]
        self.assertEqual(values,['生命值','装甲回复'])
        self.assertNotIn('数值待核实',html)
        self.assertEqual(html.count('data-icon-key="attribute_category/defense"'),2)
        for key,value in [('fixed_minor_punch_drunk_headshot_damage','20.0%'),('fixed_minor_the_hollow_man_health_damage','14.0%'),('fixed_minor_emperor_s_guard_armor_regen','1.00%')]:
            self.assertIn(value,reader.template('TD2固定词条片段',{'1':key}))


    def test_confirmed_level40_values_reach_all_fixed_exotic_references(self):
        expected={'exotic:b3cf2e92615ab3c60003639a6c96f424':['4,925 装甲回复','20.0% 受到修复'],
                  'exotic:4cdce5b25d5518350003408f5eb82b7d':['4,925 装甲回复'],
                  'exotic:b0050135668e79e60005319dc2f2754c':['4,925 装甲回复'],
                  'exotic:4cdce5b25be1b297000371c4761afe9b':['18,935 生命值']}
        reader=ExoticLuaReader()
        for uid,values in expected.items():
            with self.subTest(uid=uid):
                raw=(ROOT/identity_catalog.page(uid)['source']).read_text(encoding='utf8')
                html=reader.expand(raw,{})
                texts=[n.text for n in nodes(html,'td2-row-value')]
                for value in values:self.assertIn(value,texts)
                self.assertNotIn('td2-data-error',html)
        ordinary=reader.template('品牌次属性行',{'数量':'2','固定次属性':'ordinary_minor_health;ordinary_minor_armor_regen_flat'})
        self.assertEqual([n.text for n in nodes(ordinary,'td2-row-value')],['18,935 生命值','4,925 装甲回复'])


class NumberGroupingTests(unittest.TestCase):
    def test_grouping_preserves_units_signs_precision_and_unknowns(self):
        from tools.brand_sets.fixed_minor import display_value
        for value, unit, expected in [('4925','number','4,925'),('18935','number','18,935'),('1234567.00','number','1,234,567.00'),('-1234.50','number','-1,234.50'),('1.0','number','1.0'),('0','number','0'),('','number',''),('20.0','percent','20.0'),('1.00','percent','1.00'),('1000','seconds','1000')]:
            with self.subTest(value=value,unit=unit):self.assertEqual(display_value(value,unit),expected)

if __name__=='__main__':unittest.main()
