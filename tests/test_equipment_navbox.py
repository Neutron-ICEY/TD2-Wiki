from tools import identity as identity_catalog
import json
import re
import shutil
import tempfile
from pathlib import Path
import unittest

from tools.brand_sets.navbox import CONFIG, SOURCE, generate, markup, project, exotic_rows
from reader_test_html import nodes
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class EquipmentNavboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = project(ROOT)

    def test_all_maintained_brands_and_only_real_named_armor(self):
        registry = json.loads((ROOT / 'publishing/registry.json').read_text(encoding='utf8'))
        pages = {r['title']: r['source'] for r in registry['entries'] if r['source'].startswith('wiki/pages/brands/')}
        self.assertEqual({r['target'] for r in self.data['brands'][:-1]}, set(pages))
        self.assertEqual(len(pages), 37)
        records = identity_catalog.read_json(ROOT / 'data/equipment/records.json')['entities']
        named_count = sum(len(entity.get('collections', {}).get('具名装备资料', {}).get('rows', []))
                          for entity in records.values() if entity['template'] == '品牌套装信息')
        self.assertEqual(len(self.data['named']), named_count)
        self.assertEqual([row['target'] for row in self.data['gear_sets']], [row['page_title'] for row in identity_catalog.read_json(ROOT / 'data/gear-sets/sets.json')['sets']])
        exotics = {r['title']: r for r in registry['entries']
                   if r['kind'] == 'pages' and r['namespace'] == 0 and (r.get('related_entity') or '').startswith('exotic:')}
        self.assertEqual({r['target'] for r in self.data['exotics']}, set(exotics))
        self.assertEqual(len(self.data['exotics']), len(exotics))
        equipment = identity_catalog.read_json(ROOT / 'data/equipment/records.json')['entities']
        for item in self.data['exotics']:
            entry = exotics[item['target']]
            raw = (ROOT / entry['source']).read_text(encoding='utf8')
            self.assertTrue(raw.startswith('{{奇特装备信息\n'))
            self.assertIn('|资料ID=' + entry['related_entity'] + '\n', raw)
            fields = equipment[entry['related_entity']]['fields']
            self.assertEqual(fields['装备名称'], item['name'])
            self.assertEqual(fields['装备部位'], item['slot'])
        rendered_pages = {}
        for item in self.data['named']:
            page, anchor = item['target'].split('#')
            self.assertIn(page, pages)
            if page not in rendered_pages:
                raw = (ROOT / pages[page]).read_text(encoding='utf8')
                rendered_pages[page] = WikiSubset(ROOT).expand(raw, {})
            self.assertIn('id="' + anchor + '"', rendered_pages[page])
            entity=next(e for e in equipment.values() if e['source']==pages[page])
            record=next(r for r in entity['collections']['具名装备资料']['rows'] if r['stable_id']==anchor.removeprefix('named-'))
            self.assertEqual(record['装备部位'],item['slot'])
            self.assertNotIn('武器', item['icon'])

    def test_targeted_loot_order_and_retained_unlisted_brand(self):
        config = json.loads((ROOT / CONFIG).read_text(encoding='utf8'))
        self.assertEqual([r['entity_id'] for r in self.data['brands']][:36], config['brand_order'])
        self.assertEqual(self.data['brands'][-2]['name'], '耶尔装甲')
        extra = self.data['brands'][-1]
        self.assertEqual(extra['entity_id'], 'page:临时制作')
        self.assertEqual(extra['target'], identity_catalog.page(extra['entity_id'], ROOT)['title'])
        self.assertEqual(extra['icon'], identity_catalog.asset('equipment-improvised-icon', ROOT)['title'].split(':', 1)[1])
        entity = identity_catalog.read_json(ROOT / 'data/equipment/records.json')['entities'][extra['entity_id']]
        self.assertEqual(entity['fields']['资料类型'], 'unbranded')
        self.assertNotIn('#ifexist:', markup(self.data))

    def test_registered_gear_and_named_anchors_before_first_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in ('publishing/registry.json', 'publishing/pending-moves.json',
                             'ui/editor/src/parser.js', CONFIG, 'data/equipment/records.json',
                             'data/brand-sets/brands.json', 'data/brand-sets/equipment-ui.json',
                             'data/brand-sets/talents.json', 'data/gear-sets/sets.json',
                             'data/exotic-gear/talents.json'):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            shutil.copytree(ROOT / 'wiki/pages', root / 'wiki/pages')
            (root / 'publishing/baseline.json').write_text('{"entries":[]}', encoding='utf8')
            navigation = project(root)
        brand = '品牌套装-5.11 Tactical'
        self.assertIn(brand, {row['target'] for row in navigation['brands']})
        named = {row['name']: row['target'] for row in navigation['named']}
        self.assertEqual(named['看守人'], brand + '#named-gear_511_keeper')
        self.assertEqual(named['死亡之握'], brand + '#named-gear_511_deathgrips')
        self.assertIn('奇特装备-“土狼”的面具', {row['target'] for row in navigation['exotics']})
        self.assertEqual(navigation, self.data)

    def test_default_open_and_future_section_override(self):
        text = markup(self.data, config=json.loads((ROOT / CONFIG).read_text(encoding='utf8')))
        self.assertEqual(text.count('data-default-open="true"'), 1)
        self.assertNotIn('data-default-open="false"', text)
        self.assertEqual(text.count('class="td2-navbox-panel"'), 5)
        custom = markup(self.data, config={'default_open': True, 'section_open': {'named': False}})
        self.assertIn('data-section="named" data-default-open="false"', custom)

    def test_named_b2_grouping_and_chinese_name_order(self):
        order = ['mask', 'backpack', 'chest', 'gloves', 'holster', 'kneepads']
        slots = [r['slot'] for r in self.data['named']]
        self.assertEqual(slots, sorted(slots, key=order.index))
        self.assertEqual([slots.count(slot) for slot in order], [5, 23, 25, 7, 8, 7])
        self.assertEqual([r['name'] for r in self.data['named'][:5]], ['放轻松', '昏头胀脑', '空心人', '守夜者', '远见'])
        text = markup(self.data)
        panel = next(n for n in nodes(text, 'td2-navbox-panel') if n.attrs['data-section'] == 'named')
        self.assertEqual([n.attrs['data-slot'] for n in panel.find_all('td2-navbox-slot-group')], order)
        self.assertEqual([n.text for n in panel.find_all('td2-navbox-slot-label')], ['面具', '背包', '胸甲', '手套', '枪套', '护膝'])
        self.assertEqual(len(panel.find_all('td2-navbox-card')), len(self.data['named']))
        self.assertEqual(text.count('class="td2-navbox-panel"'), 5)
        self.assertEqual(text.count('class="td2-navbox-card"'), sum(len(rows) for rows in self.data.values()))

    def test_missing_image_keeps_name_and_link(self):
        sample = {key: [] for key in self.data}
        sample['brands'] = [{'name': 'NON-GAME-FACT', 'target': 'Test', 'icon': ''}]
        text = markup(sample)
        self.assertIn('[[Test|NON-GAME-FACT]]', text)
        self.assertNotIn('File:', text)

    def test_exotic_slots_reuse_named_cards_and_first_talent_only(self):
        icons=identity_catalog.read_json(ROOT/'data/brand-sets/equipment-ui.json')
        talents=[{'id':'first','icon':{'wiki_file':'FIRST.png','confirmed_on_wiki':False}}, {'id':'second','icon':{'wiki_file':'SECOND.png','confirmed_on_wiki':True}}]
        records=[{'title':'TEST-'+slot,'params':{'装备ID':'TEST-'+slot,'装备名称':'NON-GAME-FACT '+slot,'装备部位':slot,},'effects':[{'图标':'first'},{'图标':'second'}]} for slot in reversed(['mask','backpack','chest','gloves','holster','kneepads'])]
        rows=exotic_rows(records,talents,icons)
        self.assertEqual([r['slot'] for r in rows],['mask','backpack','chest','gloves','holster','kneepads'])
        data={k:[] for k in self.data};data['exotics']=rows
        text=markup(data)
        self.assertEqual(text.count('class="td2-navbox-slot-group"'),6)
        self.assertEqual(text.count('class="td2-navbox-slot-watermark"'),6)
        self.assertIn('[[File:FIRST.png|',text)
        self.assertNotIn('#ifexist',text)
        self.assertNotIn('SECOND.png',text)
        talents[0]['icon']={}
        self.assertTrue(all(not r['icon'] for r in exotic_rows(records,talents,icons)))
        records[0]['effects'][0]['图标']='unknown'
        with self.assertRaises(ValueError):exotic_rows(records,talents,icons)

    def test_b41_icons_and_empty_sections(self):
        brands = {r['name']: r['icon'] for r in self.data['brands']}
        slots = identity_catalog.read_json(ROOT / 'data/brand-sets/equipment-ui.json')['slot_visuals']
        named = {row['name']: row for row in self.data['named']}
        talents = {row['id']: row for row in identity_catalog.read_json(ROOT / 'data/brand-sets/talents.json')['talents']}
        for name, talent in [('看守人', 'perfect_protector'), ('斗牛犬', 'perfect_composure'), ('“零”为不乱', 'perfectly_unbreakable')]:
            self.assertEqual(named[name]['icon'], talents[talent]['icon']['wiki_file'])
        for name in ('空心人', '节日快递', '雪花机'):
            self.assertEqual(named[name]['icon'], brands[named[name]['brand']])
        for row in self.data['named']:
            self.assertEqual(row['slot_icon'], slots[row['slot']]['wiki_file'])
        text = markup(self.data)
        self.assertNotIn('#ifexist', text)
        empty = markup({key: [] for key in self.data})
        for key, label in [('exotics', '奇特装备')]:
            self.assertIn('data-section="' + key + '"><div class="td2-navbox-heading">' + label + '</div><div class="td2-navbox-body"><div class="td2-navbox-grid"></div></div></div>', empty)
        self.assertEqual(empty.count('class="td2-navbox-grid"'), 4)
        self.assertNotIn('class="td2-navbox-card"', empty)
        self.assertEqual(re.findall(r'data-section="([^"]+)"', text), ['all', 'brands', 'gear_sets', 'named', 'exotics'])
        for rendered in (text, empty):
            self.assertNotIn('暂无数据', rendered)
            self.assertNotIn('敬请期待', rendered)
        for section in ('named', 'exotics'):
            panel = next(n for n in nodes(text, 'td2-navbox-panel') if n.attrs['data-section'] == section)
            self.assertEqual(len(panel.find_all('td2-navbox-slot-watermark')), len(self.data[section]))
        sample = {k: list(v) for k, v in self.data.items()}
        sample['gear_sets'] = sample['brands'][:1]
        sample['exotics'] = [dict(sample['brands'][0], slot='mask')]
        self.assertEqual(re.findall(r'data-section="([^"]+)"', markup(sample)), ['all', 'brands', 'gear_sets', 'named', 'exotics'])

    def test_shared_template_once_and_no_category_or_editor_contract(self):
        reader = (ROOT / 'wiki/templates/品牌套装内容.wiki').read_text(encoding='utf8')
        self.assertEqual(reader.count('{{TD2装备导航}}'), 1)
        self.assertTrue(reader.rstrip().endswith('{{TD2装备导航}}\n</includeonly>'))
        text = (ROOT / SOURCE).read_text(encoding='utf8')
        self.assertNotIn('[[分类:', text)
        rendered = WikiSubset(ROOT).template('TD2装备导航', {})
        self.assertEqual(re.findall(r'<h2[^>]*>(.*?)</h2>', rendered), ['装备导航'])
        self.assertEqual(rendered.count('class="td2-navbox-card"'), sum(len(rows) for rows in self.data.values()))

    def test_projection_is_current(self):
        generate(ROOT, check=True)

    def test_reader_content_is_unchanged_before_navigation(self):
        path = 'wiki/templates/品牌套装内容.wiki'
        current = (ROOT / path).read_text(encoding='utf8')
        previous = current.replace('</div>\n{{TD2装备导航}}\n</includeonly>', '</div></includeonly>')
        page = (ROOT / 'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text(encoding='utf8')
        before = WikiSubset(ROOT, sources={path: previous}).expand(page, {})
        without_nav = WikiSubset(ROOT, sources={SOURCE: '<includeonly></includeonly>'}).expand(page, {})
        self.assertEqual(before.strip(), without_nav.strip())
