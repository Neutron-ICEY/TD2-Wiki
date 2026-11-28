import json
from pathlib import Path
import re
import unittest

from reader_test_html import nodes, weapon_unit
from tools.equipment.lua import LuaBoundary
from tools.equipment.wikitext import WikiSubset


ROOT = Path(__file__).resolve().parents[1]


class WeaponPage:
    def __init__(self, ordinary_tables=False):
        self.wiki = WikiSubset(ROOT, sources={'wiki/templates/TD2武器导航.wiki': ''})
        self.wiki.lua_boundary = LuaBoundary(self.wiki)
        self.lua = self.wiki.lua_boundary.lua
        if ordinary_tables:
            self.lua.execute('mw.loadData = require')
        self.mapping = self.lua.eval("require('Module:TD2装备映射')")
        self.models = {
            row['装备名称']: (entity_id, index, row)
            for entity_id, entity in self.mapping.entities.items() if entity.template == '武器信息'
            for index, row in entity.weapons.items()
        }
        entries = json.loads((ROOT / 'publishing/registry.json').read_text('utf8'))['entries']
        self.sources = {r['related_entity']: r['source'] for r in entries if r.get('related_entity') and r['kind'] == 'pages'}

    def model(self, name):
        return self.models[name][2]

    def article(self, name):
        entity_id, index, _ = self.models[name]
        source = (ROOT / self.sources[entity_id]).read_text('utf8')
        rendered = self.wiki.expand(source, {})
        anchor = '武器概览' if index == 1 else name
        return weapon_unit(rendered, anchor)


def acquisition(article):
    heading = '<h2><span class="mw-headline">制作与获取</span></h2>'
    return article.split(heading, 1)[1].split('<h2>', 1)[0] if heading in article else ''


class WeaponReaderBoundaryTests(unittest.TestCase):
    def test_weapon_gallery_separates_equipped_and_family_skins_from_card_art(self):
        page = WeaponPage()
        def skins(name):
            return [n.text for n in nodes(page.article(name), 'td2-weapon-skin-name')]
        self.assertEqual(skins('左边'), ['左撇子'])
        self.assertEqual(skins('ACS-12').count('霜降'), 1)
        self.assertEqual(skins('ACS-12').count('十二宫'), 1)
        self.assertNotIn('左撇子', skins('ACS-12'))
        self.assertEqual(skins('指定打击'), ['“指定打击”专用工业皮肤'])
        self.assertIn('危害区域', skins('SR-1'))
        self.assertEqual(page.model('指定打击').image, page.model('SR-1').image)
        self.assertNotEqual(page.model('左边').image, page.model('ACS-12').image)
        self.assertEqual(skins('蜜獾').count('狼人'), 1)
        self.assertNotIn('狼人', skins('狂野狼人'))
        self.assertIn('赃车兜风', skins('M249 B'))
        self.assertNotIn('“摇滚”专用河岸皮肤', skins('印花代理人'))
        self.assertIn('“摇滚”专用河岸皮肤', skins('摇滚'))
        self.assertEqual(page.model('天生伟大').image, page.model('军用 G36').image)
        self.assertEqual(page.model('雪上加霜').image, page.model('定制 L86 A2').image)
        self.assertNotEqual(page.model('雪橇弑手').image, page.model('汤米').image)
        self.assertNotEqual(page.model('白板').image, page.model('军规 L86 LSW').image)

    def test_mod_section_depends_on_visible_sockets(self):
        page = WeaponPage()
        sheriff = page.article('警长')
        self.assertIn('>改造模块<', sheriff)
        self.assertEqual([n.text for n in nodes(sheriff, 'td2-weapon-mod-value')], ['警长枪口+15.0% 暴击机率'])
        self.assertIn('aria-level="4">武器皮肤<', sheriff)
        self.assertEqual([n.text for n in nodes(sheriff.split('>武器原型<')[0], 'td2-weapon-skin-name')], ['屠宰场'])

        firestarter = page.article('火种')
        self.assertNotIn('>改造模块<', firestarter)
        self.assertNotIn('>武器皮肤<', firestarter)
        self.assertIn('>制作与获取<', firestarter)

        ak = page.article('AK-M')
        self.assertIn('>改造模块<', ak)
        self.assertEqual([n.text for n in nodes(ak, 'td2-weapon-mod-value')], ['空槽位'] * 3)
        elmo = page.article('圣艾尔莫引擎')
        self.assertLess(elmo.index('>改造模块<'), elmo.index('aria-level="4">武器皮肤<'))
        self.assertEqual(len(nodes(elmo, 'td2-weapon-mod')), 4)
        self.assertEqual([n.text for n in nodes(elmo.split('>武器原型<')[0], 'td2-weapon-skin-name')], ['极光', '电能', '红色警戒'])
        caduceus = page.article('双蛇杖')
        self.assertNotIn('（固定）', caduceus)
        self.assertEqual(len(nodes(caduceus, 'td2-weapon-mod')), 4)

    def test_exotic_original_uses_the_registered_model_and_gallery_level(self):
        page = WeaponPage()
        for exotic, original, level in [('圣艾尔莫引擎', '警用 M4', 4), ('头牌明星', '特战 Mk20 SSR', 4),
                                        ('驯鹰人', '军规 P416', 4), ('警长', 'Super 90', 4)]:
            with self.subTest(exotic=exotic):
                article = page.article(exotic)
                before, card = article.split(f'aria-level="{level}">武器原型<')
                self.assertNotIn('>武器皮肤<', card)
                self.assertNotIn('>制作与获取<', before)
                card = card.split('>制作与获取<')[0]
                self.assertEqual([n.text for n in nodes(card, 'td2-weapon-skin-name')], [original])
                self.assertIn('[[File:'+page.model(original).image+'|256px|link=顶级武器-'+original+'|alt='+original+']]', card)
        self.assertNotIn('>武器皮肤<', page.article('头牌明星'))
        for name in ['饥饿之人', '大亚历杭德罗', '警用 M4', '左边']:
            with self.subTest(name=name):
                self.assertNotIn('>武器原型<', page.article(name))

    def test_reader_keeps_dps_during_mapping_cutover(self):
        page = WeaponPage()
        stats = page.model('ACR').stats
        stats.dps = stats.dps_range = stats.fire_cycle = None
        stats.base_damage, stats.base_rpm = 100.75, 610
        self.assertIn('<dt>DPS</dt><dd>1,024</dd>', page.article('ACR'))

        stats.dps = 902
        self.assertIn('<dt>DPS</dt><dd>902</dd>', page.article('ACR'))
        stats.dps = None
        stats.dps_range = page.lua.table_from([800, 900])
        self.assertIn('<dt>DPS</dt><dd>800–900</dd>', page.article('ACR'))
        stats.dps_range = None
        stats.fire_cycle = page.lua.table_from({'mode': 'burst'})
        self.assertNotIn('<dt>连发 DPS</dt>', page.article('ACR'))
        stats.fire_cycle = stats.base_rpm = None
        self.assertNotIn('<dt>DPS</dt>', page.article('ACR'))

    def test_signature_damage_labels_and_missing_dps(self):
        page = WeaponPage()
        for name in ('K8 急流火焰喷射器', 'P-017 发射器', '十字弓', 'M32A1 连发榴弹枪', 'TAC-50 C 步枪'):
            stats = page.model(name).stats
            stats.base_rpm = stats.rpm
            article = page.article(name)
            self.assertIn('<dt>面板基础伤害</dt>', article)
            self.assertNotRegex(article, r'<dt>[^<]*DPS</dt>')
        launcher = page.article('P-017 发射器')
        self.assertIn('<dt>基础爆炸伤害</dt><dd>814,445</dd>', launcher)
        self.assertNotIn('<dt>连发周期</dt>', launcher)
        self.assertNotIn('<dt>每轮发数</dt>', launcher)
        self.assertIn('<dt>基础爆炸伤害</dt><dd>754,116</dd>', page.article('M32A1 连发榴弹枪'))
        self.assertIn('<dt>基础 DPS</dt><dd>434,000</dd>', page.article('迷你炮机枪'))

    def test_default_damage_periods_and_unnecessary_reload(self):
        page=WeaponPage()
        for name,label,value in [('复仇女神','满蓄力 DPS','293,733'),('93R','连发 DPS','819,244'),
                                 ('轻语','连发周期','321 毫秒'),('精准射手 93R','连发周期','194 毫秒'),
                                 ('精准射手 93R','连发 DPS','914,277'),('冷酷无情','双发 DPS','679,534'),
                                 ('无情','双发周期','301 毫秒'),('齿轮发条','连发周期','225–226 毫秒'),
                                 ('齿轮发条','连发 DPS','744,167'),('P320 XCompact','DPS','618,740'),
                                 ('P320 XCompact','伤害','97,696'),('齿轮发条','伤害','55,949'),
                                 ('枪弹王者','装弹时间','无需装弹'),('第一波 PF45','DPS','621,155'),
                                 ('圣艾尔莫引擎','常规装填','1.76 秒'),('圣艾尔莫引擎','空仓装填','2.04 秒')]:
            with self.subTest(name=name):
                style = ' class="td2-text-gold"' if (name, label) == ('齿轮发条', '伤害') else ''
                self.assertIn('<dt>'+label+'</dt><dd'+style+'>'+value+'</dd>',page.article(name))
        for name,values in [('火种',['+11.6%','+7.5%']),('后备猎枪',['+17.0%','+12.0%']),
                            ('犀牛左轮手枪特殊版',['+11.6%','+9.3%'])]:
            rows=nodes(page.article(name),'td2-weapon-attribute')
            self.assertEqual([r.text.split()[0] for r in rows[:2]],values)

    def test_nemesis_keeps_controls_and_only_omits_the_two_simulations(self):
        page=WeaponPage()
        article=page.article('复仇女神')
        self.assertFalse(nodes(article,'td2-weapon-charts'))
        self.assertNotIn('weapon-charts-',article)
        controls=nodes(article,'td2-weapon-control')
        self.assertEqual([n.find_all('td2-weapon-bar')[0].attrs['aria-valuetext'] for n in controls],['80.46','33'])
        self.assertEqual([n.find_all('td2-icon')[0].attrs['data-icon-key'] for n in controls],['weapon/attribute']*2)
        self.assertTrue(nodes(article,'td2-weapon-range'))
        for name in ('精准射手 93R','齿轮发条','无情','冷酷无情'):
            chart,=nodes(page.article(name),'td2-weapon-charts')
            self.assertEqual(set(json.loads(chart.attrs['data-angles'])),{'stand','move','cover','hip','blind'})
            self.assertEqual(len(json.loads(chart.attrs['data-recoil'])['groups']),8)

    def test_only_supported_signature_models_can_render_charts(self):
        page = WeaponPage()
        shard = page.lua.eval("require('Module:TD2武器图表/SignatureWeapon')")
        supported = {'迷你炮机枪': {'stand', 'move', 'hip'}, 'TAC-50 C 步枪': {'stand', 'move', 'cover', 'blind', 'hip'}}
        for name, modes in supported.items():
            with self.subTest(name=name):
                chart, = nodes(page.article(name), 'td2-weapon-charts')
                self.assertEqual(set(json.loads(chart.attrs['data-angles'])), modes)
                if name == '迷你炮机枪':
                    self.assertEqual(len(json.loads(chart.attrs['data-recoil'])['groups']), 8)
                else:
                    self.assertEqual(chart.attrs['data-recoil'], '')

        sample = shard.models[page.model('迷你炮机枪')['装备UID'].lower()]
        tac = shard.models[page.model('TAC-50 C 步枪')['装备UID'].lower()]
        tac.trace = sample.trace
        for recoil_uid in (shard.signatureRecoilUid, None):
            shard.signatureRecoilUid = recoil_uid
            chart, = nodes(page.article('TAC-50 C 步枪'), 'td2-weapon-charts')
            self.assertEqual(chart.attrs['data-recoil'], '')
            self.assertEqual(set(json.loads(chart.attrs['data-angles'])), supported['TAC-50 C 步枪'])
        for name, (_, _, model) in page.models.items():
            if model.kind != 'signature' or name in supported:
                continue
            with self.subTest(name=name):
                uid = model['装备UID'].lower()
                self.assertIsNone(shard.models[uid])
                shard.models[uid] = sample
                article = page.article(name)
                self.assertNotIn('td2-weapon-charts', article)
                self.assertNotIn('data-angles=', article)
                self.assertNotIn('data-recoil=', article)
                self.assertEqual(len(nodes(article, 'td2-weapon-bar')), 2)

        unknown_uid = 'a' * 32
        page.model('P-017 发射器')['装备UID'] = unknown_uid.upper()
        shard.models[unknown_uid] = sample
        self.assertNotIn('td2-weapon-charts', page.article('P-017 发射器'))

        # Cached shards predate the UID restriction and still supply chart payloads.
        shard.signatureChartUids = None
        self.assertNotIn('td2-weapon-charts', page.article('十字弓'))

    def test_acquisition_sections_match_on_plain_and_readonly_tables(self):
        proxy, plain = WeaponPage(), WeaponPage(ordinary_tables=True)
        name = '冷酷无情'
        actual = acquisition(proxy.article(name))
        self.assertEqual(actual, acquisition(plain.article(name)))
        for text in ('武器图纸', '图纸获取', '武器获取', '冷酷无情：外观转换', '豪华组合包'):
            self.assertIn(text, actual)
        groups, = nodes(actual, 'td2-blueprint-sources')
        self.assertEqual([el.text for el in groups.children if getattr(el, 'tag', None) == 'dt'],
                         ['重新配置图纸', '外观转换图纸'])
        for page in (proxy, plain):
            entity_id, _, model = page.models[name]
            page.mapping.acquisition[entity_id] = page.lua.table_from({'equipment': [], 'blueprint': [], 'hasBlueprint': False}, recursive=True)
            model.blueprints = page.lua.table()
            empty = acquisition(page.article(name))
            self.assertEqual([node.text for node in nodes(empty, 'td2-acquisition-result')], ['无制作图纸','暂无获取资料'])
            self.assertFalse(nodes(empty, 'td2-blueprint-sources'))
        for name, (_, _, model) in proxy.models.items():
            if model.kind == 'signature':
                with self.subTest(weapon=name):
                    actual = acquisition(proxy.article(name))
                    self.assertEqual(actual, acquisition(plain.article(name)))
                    self.assertEqual([n.text for n in nodes(actual, 'td2-source-heading')], ['武器获取'])
                    self.assertEqual([n.text for n in nodes(actual, 'td2-acquisition-result')],
                                     [model.specialization.name + '专长解锁'])

    def test_axis_labels_stop_at_100_while_line_uses_native_distance(self):
        page = WeaponPage()
        profile = page.model('ACR').stats.distance_damage[1]
        self.assertEqual((profile.optimal, profile.long), (31, 105))
        for end, expected in [(80, [0, 31, 80, 100]), (100, [0, 31, 100]), (105, [0, 31, 100])]:
            with self.subTest(end=end):
                profile.long = end
                chart, = nodes(page.article('ACR'), 'td2-weapon-range')
                ticks = chart.find_all('td2-weapon-range-mark')
                self.assertEqual([int(t.text.split()[0]) for t in ticks], expected)
                self.assertEqual([int(re.fullmatch(r'left:(\d+)%', t.attrs['style'])[1]) for t in ticks], expected)
                plot, = chart.find_all('td2-weapon-range-plot')
                self.assertIn(f'{end} 米结束', plot.attrs['aria-label'])
                points = [tuple(map(float,re.findall(r'([\d.]+)%',p.attrs['style'])))
                          for p in chart.find_all('td2-weapon-range-point')]
                self.assertEqual(points[-1][0], 100)
                self.assertAlmostEqual(points[-1][1], 90 if end<=100 else 20+70*69/74, places=4)

    def test_hud_vertices_and_physical_retention(self):
        page = WeaponPage()
        def retention_values(article):
            values = []
            for facts in nodes(article, 'td2-weapon-range-retention'):
                self.assertEqual(facts.tag, 'dl')
                self.assertIn('td2-weapon-facts', facts.attrs['class'].split())
                stat, = facts.find_all('td2-weapon-stat')
                label, value = stat.children
                self.assertEqual((label.tag, label.text, value.tag), ('dt', '最小伤害比例', 'dd'))
                values.append(value.text)
            return values

        for name, expected in [('军规 MK46','77.87%'),('步兵 MG5','72.21%'),('ACR','51.88%'),
                               ('送别','66.93%'),('复仇女神','100%'),('警长','100%')]:
            with self.subTest(name=name):
                article = page.article(name)
                self.assertEqual(retention_values(article), [expected])
        sheriff = page.article('警长')
        drop, = nodes(sheriff,'td2-range-drop')
        self.assertIn('left:100%;top:20%;width:4px;height:70%',drop.attrs['style'])
        self.assertEqual([p.attrs['style'] for p in nodes(sheriff,'td2-weapon-range-point')],
                         ['left:0%;top:20%','left:100%;top:20%','left:100%;top:90%'])
        mode = page.article('大角突击步枪')
        self.assertEqual([n.text for n in nodes(mode,'td2-weapon-range-mode')],['全自动','开镜单发'])
        self.assertEqual(retention_values(mode), ['53.40%', '71.28%'])
        data = page.model('大角突击步枪').stats.distance_damage
        data[2].retention = data[1].retention
        self.assertEqual(len(nodes(page.article('大角突击步枪'),'td2-weapon-range-retention')),1)
        data[2].optimal,data[2].long,data[2].limit = data[1].optimal,data[1].long,data[1].limit
        self.assertEqual(len(nodes(page.article('大角突击步枪'),'td2-weapon-range-plot')),1)
        crossbow = page.article('十字弓')
        self.assertTrue(nodes(crossbow,'td2-weapon-range-plot'))
        self.assertFalse(nodes(crossbow,'td2-weapon-range-retention'))
        page.model('ACR').stats.distance_damage = None
        cached_mapping = page.article('ACR')
        self.assertTrue(nodes(cached_mapping,'td2-weapon-range-plot'))
        self.assertFalse(nodes(cached_mapping,'td2-weapon-range-retention'))

    def test_control_section_requires_a_chart_meter_or_reload(self):
        page = WeaponPage()
        name = '十字弓'
        stats = page.model(name).stats
        self.assertAlmostEqual(stats.accuracy_compare, 52.72727272727272)
        self.assertEqual(stats.reload_ui, 3000)
        self.assertIn('<dt>装弹时间</dt><dd>3 秒</dd>', page.article(name))
        self.assertEqual(stats.stability_compare, 0)
        name = '复仇女神'
        stats = page.model(name).stats
        stats.accuracy_compare = stats.stability_compare = stats.reload_ui = None
        self.assertNotIn('>武器控制力<', page.article(name))
        stats.reload_ui = 1500
        stats.reload_with_mods = stats.reload_empty_with_mods = None
        article = page.article(name)
        self.assertIn('>武器控制力<', article)
        self.assertIn('<dt>装弹时间</dt><dd>1.5 秒</dd>', article)
        self.assertFalse(nodes(article, 'td2-weapon-charts'))
        self.assertFalse(nodes(article, 'td2-weapon-bar'))

        name = 'ACR'
        stats = page.model(name).stats
        stats.accuracy_compare = stats.stability_compare = stats.reload_ui = None
        article = page.article(name)
        self.assertIn('>武器控制力<', article)
        self.assertTrue(nodes(article, 'td2-weapon-charts'))
        self.assertFalse(nodes(article, 'td2-weapon-bar'))
        self.assertNotIn('<dt>装弹时间</dt>', article)
        self.assertNotIn('<dl class="td2-weapon-facts"></dl>', article)

    def test_over_maximum_stability_preserves_full_reading_and_valid_meter(self):
        article = WeaponPage().article('崭新牢靠')
        control, = [c for c in nodes(article, 'td2-weapon-control') if '稳定度' in c.text]
        meter, = control.find_all('td2-weapon-bar')
        reading, = control.find_all('td2-weapon-control-value')
        self.assertEqual(reading.text, '108.64')
        self.assertEqual(meter.attrs['aria-valuetext'], reading.text)
        self.assertEqual(meter.attrs['role'], 'meter')
        self.assertEqual([float(meter.attrs[a]) for a in ('aria-valuemin', 'aria-valuenow', 'aria-valuemax')],
                         [0, 100, 100])
        self.assertEqual(meter.children[0].attrs['style'], 'width:100%')
