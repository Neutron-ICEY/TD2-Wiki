"""Cross-check maintained weapon facts against the installed game export."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.equipment.weapons_native import WeaponNative, ROOT
from tools.equipment.weapon_projection import WeaponProjection, fixed_socket, default_fire_stats, rpm_roll_counts
from tools.equipment.wikitext import WikiSubset
from tools.identity import read_json, asset
from tools import identity


class WeaponResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mapping=read_json(ROOT/'data/equipment/native-map.json')['weapons']
        cls.bindings={b['name']:b for e in mapping for b in e['items']}
        cls.native=WeaponNative(ROOT/'resources/game/current/raw_files')
        cls.projection=WeaponProjection(cls.native)
        cls.database=read_json(ROOT/'data/equipment/records.json')['entities']
        cls.wiki=WikiSubset(ROOT)

    def row(self,name):return self.projection.row(self.bindings[name])[0]

    def test_native_base_and_named_differences(self):
        acs=self.bindings['ACS-12'];left=self.bindings['左边'];stack=self.bindings['印花代理人']
        self.assertEqual(left['base_uid'],acs['uid']);self.assertEqual(stack['base_uid'],acs['uid'])
        self.assertNotEqual(left['asset_ref'],acs['asset_ref'])
        for name in ['ACS-12','左边']:
            r=self.row(name);self.assertEqual(r['stats']['pellets'],8)
            self.assertEqual(r['stats']['dps'],903758.75)
            self.assertEqual([a.get('maximum') for a in r['attributes'][:2]],[15,12])
        r=self.row('印花代理人');self.assertEqual(r['stats']['rpm'],360);self.assertEqual(r['stats']['base_damage'],150626.453125)

    def test_fixed_mods_precision_and_native_recoil(self):
        r=self.row('圣艾尔莫引擎');s=r['stats']
        self.assertEqual(s['magazine'],40);self.assertEqual(s['magazine_with_mods'],70)
        self.assertAlmostEqual(s['reload_with_mods'],1940/1.1)
        self.assertAlmostEqual(s['headshot'],55)
        self.assertAlmostEqual(s['dps'],664671.3899739584)
        self.assertEqual(s['fixed_secondary'],{'crit_chance':[0,15],'crit_damage':[25,40],'switch_factor':[1,1.1]})
        self.assertAlmostEqual(s['reload_empty_with_mods'],2240/1.1)
        self.assertEqual(len(r['recoil']),2)
        acs=self.row('ACS-12')['recoil'][0]['values']
        self.assertEqual((acs['climb'],acs['reset'],acs['vertical_return']),(120,875,92))
        self.assertEqual((acs['cover_modifier'],acs['hip_modifier']),(.6,2.5))

    def test_fixed_talent_bonus_changes_named_magazine(self):
        self.assertEqual(self.row('摇滚')['stats']['magazine_with_mods'],30)
        self.assertEqual(self.row('左边')['stats']['magazine_with_mods'],20)
        self.assertAlmostEqual(self.row('左边')['stats']['headshot'],45)

    def test_panel_rpm_and_dps_share_fixed_bonuses_once(self):
        for name, raw, panel in [('隐形之手',680,782),('衔尾蛇',1275,1402.5),('自由',200,230)]:
            with self.subTest(weapon=name):
                stats = self.row(name)['stats']
                self.assertEqual((stats['rpm'],stats['rpm_with_mods']),(raw,panel))
                self.assertAlmostEqual(stats['dps'],stats['base_damage']*panel/60)
        self.assertNotIn('rpm_with_mods',self.row('第一波 PF45')['stats'])
        self.assertAlmostEqual(self.row('第一波 PF45')['stats']['dps'],100727.9140625*370/60)

    def test_locked_sockets_pve_passives_and_volley_units(self):
        for name,base,damage,dps in [('帕坎',71538.1640625,82268.888671875,822688.88671875),
                                      ('黑色星期五',48300.12890625,58926.157265625,834787.2279296875)]:
            s=self.row(name)['stats']
            self.assertEqual((s['base_damage'],s['damage_with_mods'],s['dps']),(base,damage,dps))
        s=self.row('饥饿之人')['stats']
        self.assertEqual((s['pellets'],s['base_damage'],s['dps']),(2,134360.296875,537441.1875))
        locked={'myIsAccessBlocked':'TRUE','myRequiredItemQuality':'Orange','myMaxItemQuality':'Exotic'}
        self.assertTrue(fixed_socket('OpticsSocket',locked,set(),'Orange'))
        self.assertFalse(fixed_socket('OpticsSocket',locked,{'Orange'},'Orange'))
        self.assertFalse(fixed_socket('OpticsSocket',locked,set(),'Blue'))
        self.assertFalse(fixed_socket('OpticsSocket',{},set(),'Orange'))
        self.assertFalse(fixed_socket('WeaponSkin',locked,set(),'Orange'))
        self.assertTrue(next(s for s in self.row('圣诞颂歌')['sockets'] if s['slot']=='OpticsSocket')['fixed'])
        self.assertEqual(self.row('迅步')['stats']['fixed_secondary']['movement_factor'],[1,1.2])
        king=self.row('枪弹王者')['stats']
        self.assertTrue(king['reload_unnecessary'])
        self.assertEqual((king['reload'],king['reload_empty'],king['dps']),(4460,4760,682555.517578125))

    def test_item_generation_preserves_variant_damage_and_attributes(self):
        for name,damage in [('艺术家工具',125865.2421875),('头牌明星',417692.21875),('潜隐',349806.90625),
                            ('炽焰',409357),('扭曲绑带',95697.6328125),('獾式',51271.2890625)]:
            row = self.row(name)
            self.assertEqual(row['stats']['base_damage'],damage)
            self.assertAlmostEqual(row['stats']['dps'],damage*row['stats']['rpm']/60)
        for name in ('艺术家工具','头牌明星'):
            row=self.row(name)
            self.assertEqual(row['attributes'][0]['maximum'],15)
        self.assertEqual(self.row('艺术家工具')['stats']['damage_max'],self.row('SIG 716 CQB')['stats']['damage_max'])
        self.assertNotEqual(self.row('艺术家工具')['stats']['damage_max'],self.row('SIG 716')['stats']['damage_max'])

    def test_level40_grants_and_named_core_comparison(self):
        for name,base,secondary in [('Maxim 9',125413.9140625,9),('犀牛左轮手枪特殊版',198306.03125,9.3),
                ('生存专家 D50',189171.609375,8),('精准射手 93R',52977.828125,9.3),
                ('火种',635715.125,7.5),('P320 XCompact',87541.0546875,5)]:
            with self.subTest(name=name):
                row=self.row(name)
                self.assertEqual([a['granted'] for a in row['attributes']],[11.6,secondary])
                self.assertEqual(row['attributes'][0]['maximum'],15)
                self.assertNotIn('maximum',row['attributes'][1])
                stats=row['stats']
                self.assertEqual(stats['base_damage'],base)
                self.assertNotIn('damage_precision',stats)
                self.assertAlmostEqual(stats['damage_with_mods'],stats['base_damage']*1.116)
                self.assertEqual(row['expertise'],[])
        boom=self.row('后备猎枪')
        self.assertEqual(boom['attributes'][0]['granted'],17)
        self.assertNotIn('granted',boom['attributes'][1])
        self.assertEqual(boom['attributes'][2]['name'],'随机属性')
        self.assertEqual(boom['stats']['damage_with_mods'],648429.4275)
        enforcer=self.row('打手')
        self.assertEqual([a['name'] for a in enforcer['attributes']],['霰弹枪伤害','对装甲的伤害'])
        self.assertNotIn('damage_with_mods',enforcer['stats'])
        self.assertAlmostEqual(enforcer['stats']['dps'],389936.34375*160/60)
        bad=copy.deepcopy(self.bindings['火种'])
        next(iter(bad['level40_preset']['attributes'].values()))['pool']='wrong pool'
        failed=self.projection.row(bad)[0]
        self.assertNotIn('dps',failed['stats'])
        self.assertTrue(failed['stats']['default_damage_pending'])

    def test_live_signature_bindings_and_expertise(self):
        live=self.native.signature_weapons()
        expected = {
            'K8 急流火焰喷射器': (26040, None, None),
            'M32A1 连发榴弹枪': (300, 754116.5, None),
            'P-017 发射器': (130, 814445.8125, None),
            'TAC-50 C 步枪': (312480, None, None),
            '十字弓': (65100, 1085927.75, None),
            '迷你炮机枪': (26040, None, 434000),
        }
        names=set(expected)
        self.assertEqual(len(live),6)
        self.assertEqual({b['name'] for b in self.bindings.values() if b['kind']=='signature'},names)
        for name in names:
            with self.subTest(name=name):
                b=self.bindings[name];r=self.row(name)
                self.assertIn(b['uid'],live)
                self.assertEqual(r['group'],'SignatureWeapon')
                self.assertEqual(r['attributes'],[])
                self.assertTrue(r['asset_ref'])
                s=r['stats']
                self.assertEqual((s['damage_ui'],s.get('base_explosion_damage'),s.get('dps')),expected[name])
                if name == 'P-017 发射器':
                    self.assertNotIn('fire_cycle', s)
                self.assertEqual(s,self.database['weapon:'+b['uid'].lower()]['collections']['武器型号资料']['rows'][0]['data']['stats'])
                self.assertEqual(len(r['expertise']),1)
                self.assertEqual(r['expertise'][0]['name'],'特有武器伤害' if name in {'M32A1 连发榴弹枪','P-017 发射器','十字弓'} else '武器伤害')
                self.assertEqual(r['expertise'][0]['formula'],{'A':0,'B':.01,'C':0})
        self.assertEqual([b['name'] for b in self.row('圣艾尔莫引擎')['expertise']],['武器伤害'])
        self.assertNotIn('5D4179F15A01C06500010394008D1FDB',live)

    def test_ruthless_page_uses_the_level_40_conversion_product(self):
        from tools.equipment.crafting import links
        catalog=identity.raw_json(ROOT/'data/equipment/crafting.json')
        conversion='4CDCE5B25C125A4700032042322ABAD4'
        reconfigure='4CDCE5B25C45DBA60003F7E302F96B71'
        binding=self.bindings['冷酷无情']
        for uid,purpose in [(conversion,'craft'),(reconfigure,'reconfigure')]:
            blueprint=catalog['blueprints'][uid]
            native=self.native.record(blueprint['source'],uid)
            target,=links(self.native,native,'myCraftedItem')
            self.assertEqual(target['target_uid'],binding['uid'])
            self.assertEqual(blueprint['targets'],[binding['uid']])
            self.assertEqual(blueprint['purpose'],purpose)
            self.assertGreaterEqual(float(blueprint['max_level']),40)
        pack,=catalog['routes']['ruthless_pack'].values()
        self.assertEqual(pack['targets'],[conversion])
        entity=self.database[catalog['items'][binding['uid']]['entity_id']]
        row,=entity['collections']['武器型号资料']['rows']
        self.assertEqual(row['data']['装备UID'],binding['uid'])
        text=self.wiki.expand((ROOT/entity['source']).read_text('utf8'),{})
        for value in ('冷酷无情：外观转换','冷酷无情：改装配置','豪华组合包','<strong>+1%</strong> 武器伤害','30级'):
            self.assertIn(value,text)
        self.assertEqual(text.count('class="td2-expertise-card"'),1)

    def test_native_damage_and_missing_curve_is_reported(self):
        binding=self.bindings['第一波 PF45']
        stats=self.row('第一波 PF45')['stats']
        self.assertEqual((stats['base_damage'],stats['rpm'],stats['damage_ui']),(100727.9140625,370,100728))
        with patch.dict(self.projection.__dict__,{'damage_scales':{}}):
            row=self.row('第一波 PF45')
            self.assertNotIn('base_damage',row['stats'])
            self.assertNotIn('dps',row['stats'])
            self.assertTrue(any(i['uid']==binding['uid'] and i['field']=='base_damage' for i in self.projection.missing))

    def test_default_burst_events_and_unresolved_inputs(self):
        for name,inside,between,period in [('93R',54,86,194),('精准射手 93R',54,86,194),
                                            ('M16A2',85,151,321),('轻语',85,151,321)]:
            s=self.row(name)['stats'];c=s['fire_cycle']
            self.assertEqual((c['rounds'],c['inside_ms'],c['between_ms'],c['period_ms']),(3,inside,between,period))
            damage=59123.2561875 if name=='精准射手 93R' else s['base_damage']
            self.assertAlmostEqual(s['dps'],damage*3000/period)
        clock=self.row('齿轮发条')['stats']
        self.assertNotIn('damage_precision',clock)
        self.assertEqual((clock['base_damage'],clock['damage_ui']),(55948.984375,55949))
        self.assertEqual(clock['fire_cycle']['inside_ms'],75)
        self.assertEqual(clock['fire_cycle']['between_range_ms'],[75,76])
        self.assertEqual(clock['fire_cycle']['period_range_ms'],[225,226])
        for dps,period in zip(clock['dps_range'],(226,225),strict=True):
            self.assertAlmostEqual(dps,clock['base_damage']*3000/period)
        rolls=rpm_roll_counts(-10,10)
        self.assertEqual(sum(rolls.values()),1<<23)
        self.assertEqual(sum(count for offset,count in rolls.items() if offset<=0),4613735)
        self.assertEqual((min(rolls),max(rolls)),(-10,9))
        mean=225+4613735/(1<<23)
        self.assertEqual(clock['fire_cycle']['mean_period_ms'],mean)
        self.assertAlmostEqual(clock['dps'],clock['base_damage']*3000/mean)
        self.assertNotIn('dps',self.row('P-017 发射器')['stats'])
        event=lambda name,rate:{'context':[{'resource_type':'FullAutoFireEvent','internal_name':name}],
                                'field':'myRPMOverride','raw_value':rate}
        primary={'rpm':600,'base_damage':100,'fire_events':['FullAutoFireEvent']}
        default_fire_stats(primary,[event('default','600'),event('scoped','120')],{})
        self.assertEqual(primary['dps'],1000)

    def test_binary_edges_share_effective_single_round_rate(self):
        for name in ('无情','冷酷无情'):
            s=self.row(name)['stats']
            self.assertEqual(s['fire_cycle'],dict(mode='binary',rounds=2,inside_ms=150,between_ms=151,period_ms=301))
            self.assertAlmostEqual(s['dps'],102269.90625*2000/301)
        buffed=dict(rpm=400,rpm_with_mods=480,base_damage=100,fire_events=['BinaryFireEvent'])
        default_fire_stats(buffed,[],{})
        self.assertEqual(buffed['fire_cycle']['period_ms'],251)
        self.assertAlmostEqual(buffed['dps'],200000/251)

    def test_charge_uses_pve_full_damage_and_recovery(self):
        s=self.row('复仇女神')['stats'];c=s['fire_cycle']
        self.assertEqual((c['charge_s'],c['auto_release_s'],c['full_charge_damage'],c['recovery_ms'],c['period_ms']),
                         (2,20,940240.0625,1201,3201))
        self.assertAlmostEqual(s['dps'],940240.0625*1000/3201)
        incomplete={'rpm':50,'base_damage':100,'fire_events':['ChargedFireEvent']}
        default_fire_stats(incomplete,[],{})
        self.assertNotIn('dps',incomplete)

    def test_named_attribute_literals_preserve_percent_and_flat_units(self):
        for weapon,label,value,unit in [('白色死神','爆头伤害',137,'%'),('拖把','击杀时回复装甲',10,'%'),('“Kard”定制 TDI','技能分阶',1,'')]:
            with self.subTest(weapon=weapon):
                attr=next(a for a in self.row(weapon)['attributes'] if a['name']==label)
                self.assertEqual((attr['maximum'],attr['unit']),(value,unit))

    def test_omitted_zero_keeps_tooltip_parameter_positions(self):
        source='hunter/game system data/juice/talent/talent_weapon_reload_from_empty_increases_mag_capacity_perfect.mtalent'
        record=self.native.record(source,'0B88A6BC5E2084DF00069BDFDD64FD7F')
        for mode,count in [('PvE','2'),('PvP','3')]:
            semantic,text=self.native.talent(record,mode)
            self.assertEqual(semantic['parameters']['2']['raw'],count)
            self.assertIn('100',text);self.assertNotRegex(text,r'\{\d+\}')

    def test_named_inventory_art_follows_the_native_binding(self):
        for name,base in [('摇滚','ACS-12'),('黑色星期五','M249 B'),('劈柴者','CTAR-21')]:
            with self.subTest(name=name):
                bindings=[self.bindings[n] for n in (name,base)]
                items=[self.native.record(b['source'],b['uid']) for b in bindings]
                weapons=[self.native.linked(item,'myWeapon') for item in items]
                for field in ('myInventoryIcon','myGraphObject'):
                    values=[self.native.scalar(w,field) for w in weapons]
                    self.assertTrue(values[0])
                    self.assertEqual(*values)
                self.assertTrue(bindings[0]['asset_ref'])
                self.assertEqual(bindings[0]['asset_ref'],bindings[1]['asset_ref'])
        self.assertNotEqual(self.bindings['左边']['asset_ref'],self.bindings['摇滚']['asset_ref'])

    def test_exotic_model_art_when_the_inventory_icon_is_shared(self):
        for name,base in [('天蝎座','SIX12'),('死亡女神','CMMG Banshee'),('逆火','SIG MPX')]:
            with self.subTest(name=name):
                exotic=self.bindings[name]
                weapons=[self.native.linked(self.native.record(b['source'],b['uid']),'myWeapon')
                         for b in (exotic,self.bindings[base])]
                self.assertEqual(*(self.native.scalar(w,'myInventoryIcon') for w in weapons))
                graph=Path(self.native.scalar(weapons[0],'myGraphObject').strip('"'))
                exported=ROOT/'resources/game/current/images/hunter/baked/ui/loose_images/generated icons/mainweapon'/(graph.stem+'.png')
                self.assertNotEqual(exotic['asset_ref'],self.bindings[base]['asset_ref'])
                self.assertEqual((ROOT/asset(exotic['asset_ref'])['source']).read_bytes(),exported.read_bytes())

    def test_weapon_item_panel_formulas(self):
        carol=self.row('圣诞颂歌')['stats']
        self.assertAlmostEqual(carol['headshot'],172)
        self.assertAlmostEqual(carol['reload_ui'],4766.666666666667)
        elmo=self.row('圣艾尔莫引擎')['stats']
        self.assertAlmostEqual(elmo['accuracy_compare'],65.29870129870129)
        self.assertAlmostEqual(elmo['stability_compare'],89.5400022)
        self.assertAlmostEqual(elmo['reload_ui'],2036.3636363636363)
        self.assertEqual(self.row('ACS-12')['stats']['reload_ui'],3350)

    def test_fixed_control_attributes_apply_like_attachment_bonuses(self):
        self.assertAlmostEqual(self.row('犀牛左轮手枪特殊版')['stats']['stability_compare'], 70.5 * 1.093)
        self.assertAlmostEqual(self.row('精准射手 93R')['stats']['reload_ui'], 1710 / 1.093)

    def test_dedicated_skins_follow_socket_tags(self):
        skins=self.row('圣艾尔莫引擎')['skins']
        self.assertEqual(len(skins),3)
        self.assertEqual({t for s in skins for t in s['tags']},{'Exotic_Skin_St_Elmo_01','Exotic_Skin_St_Elmo_02','Exotic_Skin_St_Elmo_03'})
        self.assertIn('红色警戒',[s['name'] for s in skins])
        acs_skins={s['name']:s for s in self.row('ACS-12')['skins']}
        self.assertIn('霜降',acs_skins)
        self.assertNotIn('左撇子',acs_skins)
        catalog={s['uid']:s for s in read_json(ROOT/'data/equipment/weapon-skins.json')['skins']}
        entity=next(e for e in self.database.values() if e['fields'].get('装备名称')=='圣艾尔莫引擎')
        text=self.wiki.expand((ROOT/entity['source']).read_text('utf8'),{})
        self.assertIn('>武器皮肤<',text)
        self.assertNotIn('>专属皮肤<',text)
        for skin in skins:
            binding=catalog[skin['uid']]
            self.assertEqual(skin['icon'].strip('"'),binding['native_icon'])
            native=self.native.record(skin['source'],skin['uid'])
            self.assertEqual(self.native.text(native,'myUIName'),skin['name'])
            image=asset(skin['asset_ref'])
            self.assertEqual((ROOT/image['source']).read_bytes(),(ROOT/binding['image_source']).read_bytes())
            self.assertIn('[[File:'+image['title'].split(':',1)[1]+'|256px|alt='+skin['name']+']]',text)

    def test_weapon_skin_assets_match_texture_cover_or_native_preview(self):
        from io import BytesIO
        from PIL import Image
        from tools.equipment.weapon_skin_swatches import IMAGES, render_swatch
        assets = {r['id']: ROOT / r['source'] for r in identity.registry(ROOT) if r['kind'] == 'assets'}
        skins = identity.raw_json(ROOT / 'data/equipment/weapon-skins.json')['skins']
        for skin in skins:
            with self.subTest(skin=skin['name']):
                item = self.native.record(skin['source'], skin['uid'])
                texture = next((self.native.scalar(item, field).strip('"')
                                for field in ('myCustomPreviewTexture', 'myIcon')
                                if (self.native.scalar(item, field) or '').strip('"')), None)
                if texture:
                    source = IMAGES / Path(texture.lower()).with_suffix('.png')
                    self.assertEqual(source.as_posix(), skin['image_source'].lower())
                    expected = (ROOT / source).read_bytes()
                else:
                    expected, provenance = render_swatch(self.native, item)
                    with Image.open(BytesIO(expected)) as swatch:
                        self.assertEqual(swatch.size, (256, 128))
                        self.assertEqual(swatch.mode, 'RGB')
                    for key, value in provenance.items():
                        self.assertEqual(skin[key], value)
                self.assertEqual(assets[skin['asset_ref']].read_bytes(), expected)

    def test_signature_skins_use_native_type_and_exact_images(self):
        catalog={s['uid']:s for s in read_json(ROOT/'data/equipment/weapon-skins.json')['skins']}
        counts={'M32A1 连发榴弹枪':1,'K8 急流火焰喷射器':2,'迷你炮机枪':2,
                'TAC-50 C 步枪':2,'十字弓':1,'P-017 发射器':1}
        for name,count in counts.items():
            with self.subTest(weapon=name):
                row=self.row(name)
                tags={tag for slot in row['sockets'] if slot['slot']=='WeaponSkin' for tag in slot['tags']}
                types=[]
                for skin in row['skins']:
                    self.assertTrue(tags.issuperset(skin['tags']) and skin['tags'])
                    native=self.native.record(skin['source'],skin['uid'])
                    types.append(native['resource_type'])
                    binding=catalog[skin['uid']]
                    self.assertEqual(self.native.text(native,'myUIName','en'),binding['english_name'])
                    self.assertEqual(self.native.text(native,'myUIName'),skin['name'])
                    preview=(self.native.scalar(native,'myCustomPreviewTexture') or '').strip('"')
                    texture=preview or self.native.scalar(native,'myIcon').strip('"')
                    icon=Path(texture).with_suffix('.png')
                    original=ROOT/'resources/game/current/images'/icon
                    self.assertEqual(original.resolve(),(ROOT/binding['image_source']).resolve())
                    self.assertEqual(original.read_bytes(),(ROOT/asset(skin['asset_ref'])['source']).read_bytes())
                self.assertEqual(set(types),{'WeaponTransmogItem','WeaponSkinItem'})
                self.assertEqual(types.count('WeaponTransmogItem'),count)

    def test_underboss_unreleased_skin_is_a_known_empty_gallery(self):
        binding=self.bindings['副手']
        start=len(self.projection.missing)
        row=self.row('副手')
        self.assertEqual(row['skins'],[])
        self.assertFalse(any(i['uid']==binding['uid'] and i['field']=='skins' for i in self.projection.missing[start:]))
        stored=self.database['weapon:'+binding['uid'].lower()]['collections']['武器型号资料']['rows'][0]['data']
        self.assertEqual(stored['skins'],row['skins'])
        self.assertEqual(stored['base_uid'],self.bindings['汤米']['uid'])


if __name__=='__main__':unittest.main()
