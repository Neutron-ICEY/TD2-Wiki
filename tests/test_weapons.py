import re
import unittest
from tools.equipment.weapons_native import ROOT
from tools.equipment.weapons import check_title, named_entry_id, named_redirects, navigation
from tools.equipment.lua import LuaBoundary
from tools.equipment.wikitext import WikiSubset
from tools.identity import read_json, asset
from tools import identity
from tools.brand_sets.icons import weapon_talent_icons
from reader_test_html import weapon_unit
from tools.equipment.weapon_projection import WeaponProjection


class ReviewedWeaponMaximaTests(unittest.TestCase):
    def test_only_matching_slots_inherit_an_adopted_maximum(self):
        projection = WeaponProjection.__new__(WeaponProjection)
        slot = dict(id='attribute', core=True, named=False, percentile='-1')
        adopted = dict(maximum=15, unit='%', reference_field='reviewed source')
        projection.reviewed_attributes = {('weapon', 'normal'): [{**slot, **adopted}]}
        attributes = [dict(slot), dict(slot, maximum=12), dict(slot, named=True), dict(slot, granted=7)]
        projection.retain_reviewed_maxima('weapon', 'normal', attributes)
        self.assertEqual(attributes[0], {**slot, **adopted})
        self.assertEqual(attributes[1], {**slot, 'maximum': 12})
        self.assertNotIn('maximum', attributes[2])
        self.assertNotIn('maximum', attributes[3])
        for uid, kind in [('new weapon', 'normal'), ('weapon', 'exotic')]:
            new = [dict(slot)]
            projection.retain_reviewed_maxima(uid, kind, new)
            self.assertEqual(new, [slot])


class WeaponsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping=read_json(ROOT/'data/equipment/native-map.json')['weapons']
        cls.bindings={b['name']:b for e in cls.mapping for b in e['items']}
        cls.database=read_json(ROOT/'data/equipment/records.json')['entities']
        cls.wiki=WikiSubset(ROOT)

    def test_fixed_talent_images_match_the_shared_uid_catalog_in_both_modes(self):
        icons=weapon_talent_icons(ROOT)
        checked=set()
        for entity in self.database.values():
            if entity['template']!='武器信息':
                continue
            for effect in entity['effects']:
                uid=effect['效果ID'].removeprefix(effect['所属装备']+'_')
                key='weapon_talent_'+uid
                self.assertEqual(effect['图标'],key if key in icons else '',(entity['page_title'],effect['模式'],uid))
                if key in icons and key not in checked:
                    image=self.wiki.template('TD2图标',{'类别':'talent','键':key,'用途':'optional'})
                    self.assertIn('File:'+icons[key]['wiki_file']+'|80x80px',image)
                    checked.add(key)
        self.assertIn('weapon_talent_9e75f5ef67ecfa05000d5f4eef038497',checked)

    def test_all_navigation_targets_and_registered_images(self):
        text=navigation();targets=re.findall(r'data-target="([^"]+)"',text)
        self.assertEqual(re.findall(r'<h2[^>]*>(.*?)</h2>', text), ['武器导航'])
        self.assertIn('class="td2-navbox-heading">特有武器</div>', text)
        self.assertEqual(len(targets),len(set(targets)))
        entities={e['page_title']:e for e in self.database.values() if e['template']=='武器信息'}
        count=0
        for target in targets:
            title,_,anchor=target.partition('#');e=entities[title]
            rows=[r['data'] for r in e['collections']['武器型号资料']['rows']]
            if anchor:self.assertIn(anchor,[r['装备名称'] for r in rows[1:]])
            count+=1
        self.assertEqual(count,sum(len(e['items']) for e in self.mapping))
        for e in self.mapping:
            for b in e['items']:
                if b.get('asset_ref'):self.assertTrue((ROOT/asset(b['asset_ref'])['source']).is_file())
        self.assertNotIn('#ifexist',text)

    def test_canonical_weapon_titles_and_named_entrances(self):
        prefixes={'normal':'顶级武器','exotic':'奇特武器','signature':'特有武器','named':'具名武器'}
        def expected_title(model, title):
            prefix = prefixes[model['kind']] + '-' + model['装备名称']
            self.assertRegex(title, '^' + re.escape(prefix) + r'(?:（[^（）]+）)?$')

        entrances={r['id']:r for r in identity.registry(ROOT) if r['kind']=='redirects' and r['source'].startswith('wiki/redirects/weapons/')}
        expected=set()
        for entity_id, entity in self.database.items():
            if entity['template']!='武器信息':continue
            models=[record['data'] for record in entity['collections']['武器型号资料']['rows']]
            main,=(m for m in models if m['kind']!='named')
            expected_title(main, entity['page_title'])
            for m in models:
                if m['kind']!='named':continue
                key=named_entry_id(m)
                self.assertNotIn(key,expected)
                expected.add(key)
                entry=entrances[key]
                self.assertEqual(entry['related_entity'],entity_id)
                expected_title(m,entry['title'])
                self.assertEqual((ROOT/entry['source']).read_text('utf8'),'#REDIRECT [['+entity['page_title']+'#'+m['装备名称']+']]\n')
        self.assertEqual(entrances.keys(),expected)

    def test_title_qualifiers_do_not_hide_duplicate_named_sections(self):
        base = {'kind':'normal','装备名称':'基准','装备UID':'AA'}
        named = {'kind':'named','装备名称':'同名','装备UID':'BB','base_uid':'AA'}
        check_title('具名武器-同名（步枪）', named)
        for title in ('同名','奇特武器-同名','具名武器-同名（）','具名武器-同名（ ）'):
            with self.subTest(title=title), self.assertRaises(ValueError):
                check_title(title,named)
        models = [base,named,{**named,'装备UID':'CC'}]
        entities = {'weapon:aa':{'template':'武器信息','page_title':'顶级武器-基准',
                    'collections':{'武器型号资料':{'rows':[{'data':m} for m in models]}}}}
        registry = {'entries':[{'kind':'redirects','id':named_entry_id(m),'source':'wiki/redirects/weapons/'+m['装备UID']+'.wiki',
                     'generator':'tools/equipment/weapons.py@v1','related_entity':'weapon:aa','title':'具名武器-同名（'+m['装备UID']+'）'}
                     for m in models[1:]]}
        with self.assertRaisesRegex(ValueError,'Duplicate named weapon anchor'):
            named_redirects(entities,registry)

    def test_weapon_records_share_the_identity_validator(self):
        report=identity.validate(check_bytes=False)
        self.assertEqual(report['entities'],len(self.database))

    def test_navigation_uses_talent_and_ammo_icons(self):
        text=navigation()
        def card(target):
            return text.split('data-target="'+target+'"',1)[1].split('</div>',1)[0]
        self.assertNotIn('td2-navbox-parent',text)
        left=card('顶级武器-ACS-12#左边')
        self.assertIn('PerfectSledgehammer-Icon',left)
        self.assertIn('td2-navbox-talent',left)
        rock=card('顶级武器-ACS-12#摇滚')
        image=asset(self.bindings['ACS-12']['asset_ref'])['title']
        self.assertIn('td2-navbox-icon">[['+image+'|',rock)
        self.assertIn('PerfectlyExtra-Icon',rock)
        for target,icon in [('顶级武器-经典 M44 卡宾枪#圣诞颂歌','TwinklingLights'),
                            ('顶级武器-PDR#初次绽放','BlossomHarvest')]:
            item=card(target)
            self.assertIn('td2-navbox-talent',item)
            self.assertIn('TD2-Talent-Weapon-'+icon+'-Icon.png',item)
        item=card('顶级武器-ACS-12#印花代理人')
        self.assertNotIn('td2-navbox-talent',item)
        self.assertIn('td2-navbox-slot-watermark',item)
        for name,talent in [('圣艾尔莫引擎','ActumEst'),('天蝎座','SepticShock')]:
            exotic=card('奇特武器-'+name)
            image=asset(self.bindings[name]['asset_ref'])['title']
            self.assertIn('td2-navbox-icon">[['+image+'|',exotic)
            self.assertIn('td2-navbox-talent" aria-hidden="true">[[File:TD2-Talent-ExoticWeapon-'+talent+'-Icon.png|',exotic)

    def test_shared_reader_named_anchors_dps_and_notes(self):
        e=next(e for e in self.database.values() if e['fields'].get('装备名称')=='ACS-12')
        raw=(ROOT/e['source']).read_text('utf8');text=self.wiki.expand(raw,{})
        self.assertEqual(text.count('id="左边"'),1);self.assertEqual(text.count('id="印花代理人"'),1)
        self.assertEqual(text.count('>武器属性<'),1)
        self.assertNotRegex(text, r'</?(?:article|section)\b')
        self.assertIn('aria-level="4">核心数值<',weapon_unit(text,'左边'))
        self.assertNotIn('复制链接',text)
        self.assertNotIn('td2-weapon-index',text)
        self.assertIn('903,758',text)
        self.assertNotIn('仅供参考',text);self.assertNotIn('不计换弹',text)
        self.assertEqual(text.count('class="td2-navbox td2-weapon-navbox"'),1)
        self.assertIn('td2-brand-infobox-frame',text)
        self.assertIn('td2-weapon-named-list',text)
        self.assertNotIn('提升精通等阶',text)
        e=next(e for e in self.database.values() if e['fields'].get('装备名称')=='圣艾尔莫引擎')
        text=self.wiki.expand((ROOT/e['source']).read_text('utf8'),{})
        self.assertIn('<dt>DPS</dt><dd>664,671</dd>',text)
        self.assertIn('<dt>伤害</dt><dd>46,918</dd>',text)
        self.assertIn('绝缘弹匣',text);self.assertIn('class="td2-weapon-charts"',text);self.assertNotIn('<summary>后坐力</summary>',text)
        self.assertLess(text.index('>属性<'),text.index('>天赋<'))
        self.assertLess(text.index('>天赋<'),text.index('>武器控制力<'))
        self.assertIn('<dt>每分钟射速</dt>',text);self.assertIn('<dt>DPS</dt>',text)
        self.assertNotIn('发/分钟',text);self.assertNotIn('基础 DPS',text)
        self.assertIn('weapon/core_attribute',text);self.assertIn('weapon/optics',text)
        self.assertIn('state/proficient',text);self.assertIn('td2-weapon-range-plot',text)
        self.assertNotIn('<meter',text)
        self.assertNotIn('<div class="td2-acquisition-result"><div class="td2-acquisition-result">',text)

    def test_acs_named_sections_and_shared_expertise(self):
        entity_id='weapon:'+self.bindings['ACS-12']['uid'].lower()
        raw=(ROOT/self.database[entity_id]['source']).read_text('utf8')
        wiki=WikiSubset(ROOT)
        wiki.lua_boundary=LuaBoundary(wiki)
        models=wiki.lua_boundary.lua.globals().require('Module:TD2装备映射').entities[entity_id].weapons
        text=wiki.expand(raw,{})
        self.assertEqual(text.count('td2-expertise-card'),1)
        last = weapon_unit(text, '印花代理人')
        self.assertGreater(text.index('td2-expertise-card'),text.index(last) + len(last))
        self.assertEqual(text.count('class="td2-weapon-named-divider"'),2)
        self.assertEqual(re.findall(r'class="td2-weapon-named-divider"[^>]*></div><div [^>]*id="([^"]+)"',text),['摇滚','印花代理人'])
        left=weapon_unit(text,'左边')
        self.assertIn('data-angles="{',left)
        self.assertIn('data-recoil="{',left)
        models[2].expertise_max_level=25
        different_cap=wiki.expand(raw,{})
        self.assertEqual(different_cap.count('td2-expertise-card'),4)
        self.assertIn('25级',weapon_unit(different_cap,'左边'))
        models[2].expertise_max_level=None
        models[2].expertise[1].formula.B=.02
        different_bonus=wiki.expand(raw,{})
        self.assertEqual(different_bonus.count('td2-expertise-card'),4)
        self.assertIn('+2%',weapon_unit(different_bonus,'左边'))

    def test_inline_talents_and_named_stat_colors(self):
        def page(name):
            entity=next(e for e in self.database.values() if e['fields'].get('装备名称')==name)
            return self.wiki.expand((ROOT/entity['source']).read_text('utf8'),{})
        text=page('ACS-12')
        def unit(anchor):return weapon_unit(text,anchor)
        for anchor in ['武器概览','印花代理人']:
            part=unit(anchor)
            self.assertNotIn('天赋位',part)
            self.assertIn('<div class="td2-random-talent">随机武器天赋</div>',part)
            self.assertEqual(part.count('>天赋<'),1)
            self.assertLess(part.index('>属性<'),part.index('>天赋<'))
            self.assertLess(part.index('>天赋<'),part.index('>武器控制力<'))
            talent=part.split('>天赋<',1)[1].split('>武器控制力<',1)[0]
            self.assertNotIn('td2-talent-icon',talent)
            self.assertNotIn('data-icon-key',talent)
            self.assertNotIn('td2-text-gold',talent)
        for anchor in ['左边','摇滚']:
            part=unit(anchor)
            self.assertEqual(part.count('>天赋<'),1)
            self.assertNotIn('天赋位',part)
            self.assertNotIn('随机武器天赋',part)
            self.assertLess(part.index('>属性<'),part.index('>天赋<'))
            self.assertLess(part.index('>天赋<'),part.index('>武器控制力<'))
            self.assertEqual(part.count('class="td2-talent-icon"'),2)  # PvE/PvP talent.
            self.assertNotIn('<dd class="td2-text-gold">',part)
        self.assertIn('talent/weapon_talent_6cfec5e662c29a9b000364548a4a662d',unit('左边'))
        stack=unit('印花代理人')
        self.assertIn('<dt>伤害</dt><dd class="td2-text-gold">150,626</dd>',stack)
        self.assertIn('<dt>每分钟射速</dt><dd class="td2-text-gold">360</dd>',stack)
        self.assertEqual(stack.count('<dd class="td2-text-gold">'),2)
        self.assertNotIn('<dd class="td2-text-gold">',unit('武器概览'))
        self.assertIn('随机武器天赋',page('ACR'))
        exotic=page('圣艾尔莫引擎')
        self.assertEqual(exotic.count('>天赋<'),1);self.assertNotIn('天赋位',exotic)
        self.assertNotIn('随机武器天赋',exotic)
        self.assertIn('id="td2-effect-',exotic)


if __name__=='__main__':unittest.main()
