from tools import identity as identity_catalog
"""Published image wiring contracts; fixtures and UI roles are not game roll facts."""
import copy
import json
import re
from tools.brand_sets.icons import mappings, resolver_source
from pathlib import Path
import unittest
from wiki_subset import WikiSubset
from reader_test_html import nodes

ROOT=Path(__file__).resolve().parents[1]

class ReaderImagePublicationTests(unittest.TestCase):
    def setUp(self):
        self.ui=identity_catalog.read_json(ROOT/'data/brand-sets/equipment-ui.json')
        self.core=identity_catalog.read_json(ROOT/'data/brand-sets/core-icons.json')
        self.files={'File:'+x['wiki_file'] for x in self.ui['slot_visuals'].values()}
        self.files.update('File:'+x['wiki_file'] for key,x in self.ui['state_icons'].items() if x['wiki_file'] and (key != 'none' or x.get('confirmed_on_wiki')))
        self.files.update('File:'+x['wiki_file'] for x in self.ui['icons'].values() if x['wiki_file'])
        self.files.update('File:'+x['wiki_file'] for x in self.core['icons']['minor'].values())
        self.wiki=WikiSubset(ROOT,existing_files=self.files)

    def test_six_slots_use_known_files_without_remote_existence_checks(self):
        self.assertEqual(set(self.ui['slot_visuals']), {'mask','chest','holster','backpack','gloves','kneepads'})
        for slot,icon in self.ui['slot_visuals'].items():
            with self.subTest(slot=slot):
                params={'类别':'equipment_slot','键':slot,'用途':'heading'}
                heading=self.wiki.template('TD2图标',params)
                visual=self.wiki.template('TD2装备视觉',{'部位':slot})
                self.assertIn('[[File:'+icon['wiki_file']+'|64x64px',heading)
                self.assertIn('[[File:'+icon['wiki_file']+'|128x128px',visual)
                self.assertIn('[[File:'+icon['wiki_file']+'|64x64px',WikiSubset(ROOT).template('TD2图标',params))
                entries={'equipment_slot/'+slot:{'wiki_file':'NON-GAME-FACT.png','confirmed_on_wiki':False}}
                sources={'wiki/templates/TD2图标.wiki':resolver_source(entries)}
                for files in ((), ('File:NON-GAME-FACT.png',)):
                    output=WikiSubset(ROOT,existing_files=files,sources=sources).template('TD2图标',params)
                    self.assertIn('[[File:NON-GAME-FACT.png|64x64px|', output)
                    self.assertNotIn('td2-icon-placeholder', output)
                    self.assertIn('data-icon-key="equipment_slot/'+slot+'"',output)
        self.assertNotIn('[[File:',self.wiki.template('TD2装备视觉',{'部位':'unknown'}))

    def test_random_zero_and_unknown_mod_counts_remain_distinct(self):
        params={'标签':'插件槽','图标':'mod_slot','状态图标':'random','无槽位内容':'无插件槽位','内容':'装备改装槽位'}
        positive=self.wiki.template('TD2装备槽行',dict(params,数量='2'))
        zero=self.wiki.template('TD2装备槽行',dict(params,数量='0'))
        unknown=self.wiki.template('TD2装备槽行',dict(params,数量=''))
        random=self.ui['state_icons']['random']['wiki_file']
        self.assertIn('[[File:'+random+'|',positive)
        self.assertNotIn('[[File:'+random+'|',zero)
        self.assertNotIn('[[File:'+random+'|',unknown)
        self.assertIn('无插件槽位',zero)
        self.assertIn('待核实',unknown)

    def test_minor_icons_do_not_replace_main_or_bonus_categories(self):
        for color in ('red','blue','yellow'):
            result=self.wiki.template('TD2原生核心图标',{'类型':'minor','颜色':color})
            self.assertIn('[[File:'+self.core['icons']['minor'][color]['wiki_file']+'|',result)
            self.assertNotIn('TD2-UI-'+color.capitalize()+'-Icon.png',result)
            self.assertEqual(self.ui['state_icons'][color]['wiki_file'],'TD2-UI-'+color.capitalize()+'-Icon.png')
        categories=identity_catalog.read_json(ROOT/'data/brand-sets/category-icons.json')
        self.assertEqual({k:v['wiki_file'] for k,v in categories['icons'].items()},{'offense':'TD2-UI-CoreMinorRed-Icon.png','defense':'TD2-UI-CoreMinorBlue-Icon.png','utility':'TD2-UI-CoreMinorYellow-Icon.png'})

    def test_approved_navigation_row_does_not_create_talent_entity(self):
        self.assertEqual(self.ui['icons']['talent_slot']['wiki_file'],'TD2-UI-TalentSlot-Icon.png')
        for identity in ('missing_formal_identity','talent_slot','天赋导航'):
            result=self.wiki.template('TD2图标',{'类别':'talent','键':identity})
            self.assertIn('td2-icon-placeholder',result)
            self.assertNotIn('[[File:',result)
        for name,key in [('talents','talents'),('fixed-minor-presets','presets')]:
            rows=json.loads((ROOT/'data/brand-sets'/ (name+'.json')).read_text(encoding='utf-8'))[key]
            self.assertTrue(rows)
            self.assertTrue({'missing_formal_identity','talent_slot','天赋导航'}.isdisjoint(row['id'] for row in rows))

    def test_white_image_rules_do_not_target_infobox_or_main(self):
        css=(ROOT/'ui/brand-sets/brand-sets.css').read_text(encoding='utf-8')
        rules=re.findall(r'([^{}]+)\{([^{}]*)\}',re.sub(r'/\*.*?\*/','',css,flags=re.S))
        shadow=[(selectors,body) for selectors,body in rules if 'filter:' in body and 'drop-shadow(1px 1px 0 rgba(0, 0, 0, 0.8))' in body]
        self.assertEqual(len(shadow),1)
        selectors,body=shadow[0]
        self.assertEqual({s.strip() for s in selectors.split(',')}, {'.td2-brand .td2-icon[data-icon-key="'+key+'"] img' for key in ('equipment_row/major_attribute','equipment_row/minor_attribute','state/random','state/gear_mod_slot','state/craft','equipment_row/mod_slot')})
        self.assertEqual(body.count('filter:'),1)
        transparent=[s for s,b in rules if 'background-color: transparent' in b]
        self.assertTrue(any('data-icon-key="equipment_row/mod_slot"' in s for s in transparent))
        self.assertIn('.td2-brand .td2-slot-image',css)
        for unexpected in ('infobox','state/red','state/blue','state/yellow','Common.css'):
            self.assertNotIn(unexpected,selectors)

    def test_approved_ui_symbols_and_offline_parity(self):
        from tools.brand_sets.icons import UI_SYMBOLS, html_icon
        expected={'state/none','state/unknown','state/drop','state/craft','state/named','material/brand_material','material/unverified'}
        self.assertTrue(expected.issubset(UI_SYMBOLS))
        entries={key:{'wiki_file':'','confirmed_on_wiki':False} for key in expected}
        fallback=WikiSubset(ROOT,sources={'wiki/templates/TD2图标.wiki':resolver_source(entries)})
        for key in expected:
            category,name=key.split('/')
            actual=self.wiki.template('TD2图标',{'类别':category,'键':name})
            offline=html_icon(category,name)
            missing=fallback.template('TD2图标',{'类别':category,'键':name})
            for output in (actual,offline,missing):
                self.assertIn('data-icon-key="'+key+'"',output)
                self.assertNotIn('➖',output)
            for output in (offline,missing):
                self.assertIn('>'+UI_SYMBOLS[key]+'</span>',output)
                self.assertTrue(UI_SYMBOLS[key].strip())
                self.assertNotIn('[[File:',output)
                self.assertNotIn('td2-icon-placeholder',output)
        self.assertIn('td2-icon-placeholder',html_icon('talent','unverified_entity'))

    def test_approved_attribute_row_images_and_unknown_minor_display(self):
        for name, filename in (('major_attribute', 'TD2-UI-MajorAttribute-Icon.png'), ('minor_attribute', 'TD2-UI-Random-Icon.png')):
            self.assertIn(filename, self.wiki.template('TD2图标', {'类别':'equipment_row', '键':name}))
        params={'标签':'次属性', '图标':'minor_attribute', '数量':''}
        text=self.wiki.template('TD2装备槽行', params)
        self.assertIn('data-icon-key="state/random"', text)
        self.assertIn('未配置／待核实', text)
        self.assertNotIn('随机任意加成', text)
        self.assertNotIn('data-icon-key="state/unknown"', text)
        other=self.wiki.template('TD2装备槽行', dict(params, 图标='mod_slot'))
        self.assertIn('data-icon-key="state/unknown"', other)

    def test_none_unknown_random_do_not_collapse(self):
        for label in ('插件槽', '天赋位'):
            with self.subTest(label=label):
                params={'标签':label,'无槽位内容':'无'+label,'图标':'mod_slot','状态图标':'random'}
                outputs=[self.wiki.template('TD2装备槽行',dict(params,数量=count)) for count in ('0','','1')]
                for output,state,word in zip(outputs,('none','unknown','random'),('无'+label,'未配置／待核实','待核实')):
                    value=nodes(output,'td2-row-value')[0]
                    self.assertEqual([n.attrs['data-icon-key'] for n in value.find_all('td2-icon')], ['state/'+state])
                    self.assertIn(word,value.text)
                    self.assertNotIn('➖',output)
                self.assertIn('[[File:'+self.ui['state_icons']['none']['wiki_file']+'|',outputs[0])
                self.assertIn('>?</span>',outputs[1])
                self.assertIn('TD2-UI-Random-Icon.png',outputs[2])

if __name__=='__main__':unittest.main()
