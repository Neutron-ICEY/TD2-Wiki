from current_identity import entity_id
from tools import identity
import copy
import json
import re
import unittest
from pathlib import Path
from tools.brand_sets.random_crafting import load, for_brand, render, validate, lua_source
from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class RandomBrandCraftingTests(unittest.TestCase):
    def test_native_pools_are_slot_specific(self):
        data = load(ROOT)
        pools = {r['slot']: {data['brands'][t['brand_uid']]['name'] for t in r['targets']} for r in data['recipes']}
        self.assertEqual(len(data['recipes']), 6)
        self.assertEqual(sum(map(len, pools.values())), 32)
        self.assertEqual(len(set(map(frozenset, pools.values()))), 6)
        self.assertEqual(pools['chest'], {'芬里斯集团公司', '霸主军备公司', '彼得罗夫防御集团', '天命防御公司', '索寇罗夫企业', '耶尔装甲'})
        self.assertEqual({r['slot'] for r in for_brand(entity_id('耶尔装甲'), data=data)}, {'mask', 'chest'})
        self.assertEqual(for_brand('临时制作', 'unbranded', data), [])
        self.assertEqual(for_brand(entity_id('耶尔装甲'), 'unbranded', data), [])
        self.assertEqual(for_brand('unknown', data=data), [])

    def test_invalid_identity_and_duplicate_recipe_fail(self):
        data = load(ROOT)
        bad = copy.deepcopy(data)
        bad['recipes'][0]['targets'][0]['brand_uid'] = 'F' * 32
        with self.assertRaises(AssertionError): validate(bad)
        bad = copy.deepcopy(data)
        bad['recipes'].append(bad['recipes'][0])
        with self.assertRaises(AssertionError): validate(bad)
        self.assertEqual((ROOT/'wiki/modules/TD2随机品牌制作数据.lua').read_text('utf-8'), lua_source(data))

    def test_all_37_brands_and_improvised_only_gain_slot_rows(self):
        template = 'wiki/templates/品牌套装内容.wiki'
        source = (ROOT/template).read_text('utf-8')
        pattern = r'{{#invoke:TD2品牌投影\|randomCrafting\|brand={{{映射名称\|}}}\|kind={{{资料类型\|}}}\|slot=([a-z]+)}}'
        self.assertEqual(len(re.findall(pattern, source)), 6)
        acquisition = identity.read_json(ROOT/'data/brand-sets/acquisition-methods.json')
        old = WikiSubset(ROOT, sources={template: re.sub(pattern, '', source)}, acquisition=acquisition)
        new = WikiSubset(ROOT, acquisition=acquisition)
        paths = list((ROOT/'wiki/pages/brands').glob('*.wiki')) + [ROOT/'wiki/pages/equipment/装备规则-临时制作.wiki']
        self.assertEqual(len(paths), 38)
        affected = total = 0
        for path in paths:
            raw = path.read_text('utf-8')
            after, before = new.expand(raw, {}), old.expand(raw, {})
            name = re.search(r'\|资料ID=([^\n|}]+)',raw)[1]
            recipes = for_brand(name, 'unbranded' if path.stem == '临时制作' else '')
            if recipes: affected += 1
            total += len(recipes)
            rows = re.findall(r'<dt>(.*?)</dt><dd>(.*?)</dd>', after, re.S)
            blueprint_rows = [(title, body) for title,body in rows if title.endswith('图纸')]
            self.assertEqual(len(blueprint_rows), 6, path.name)
            for slot,(title,body) in zip(['mask','backpack','chest','gloves','holster','kneepads'],blueprint_rows):
                block = render(name, 'unbranded' if path.stem == '临时制作' else '', slot, icon='<span class="td2-icon">[[File:TD2-UI-LoadoutCircle-Icon.png|24x24px|link=|alt=]]</span>')
                self.assertEqual(body.count('随机品牌制作'), int(bool(block)), (path.name,slot))
                if block:
                    self.assertTrue(body.endswith(block))
                    self.assertNotIn('<a', block)
                    after = after.replace(block, '', 1)
            self.assertEqual(after, before, path.name)
        self.assertEqual((affected,total), (15,32))

    def test_dedicated_and_absent_blueprint_rows(self):
        engine = WikiSubset(ROOT, acquisition=identity.read_json(ROOT/'data/brand-sets/acquisition-methods.json'))
        for value in ['', '测试图纸']:
            raw = '{{品牌套装内容|映射名称='+entity_id('耶尔装甲')+'|套装全称=耶尔装甲|mask图纸=' + value + '}}'
            expanded = engine.expand(raw,{})
            self.assertEqual(expanded.count('随机品牌制作'), 2)
            self.assertIn(value or '无制作图纸', expanded)
            self.assertNotIn('<h3>随机品牌制作', expanded)
