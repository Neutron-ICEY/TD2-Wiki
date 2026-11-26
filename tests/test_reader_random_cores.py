import re
import unittest
from pathlib import Path

from wiki_subset import WikiSubset

ROOT = Path(__file__).resolve().parents[1]


class RandomCoreReaderTests(unittest.TestCase):
    def setUp(self):
        self.wiki = WikiSubset(ROOT)

    def major(self, values, triple='否'):
        return self.wiki.template('TD2主属性列表', {'1': values, '同时拥有主核心': triple, '部位': 'backpack'})

    def test_fixed_single_is_exact_existing_template(self):
        for core in ('red', 'blue', 'yellow'):
            with self.subTest(core=core):
                self.assertEqual(self.major(core).strip(), self.wiki.template('TD2主属性显示', {'1': core}).strip())

    def test_random_candidates_are_sorted_icons_without_fixed_values(self):
        for values, expected in [('yellow;red', ['red', 'yellow']), ('yellow;blue', ['blue', 'yellow']), ('blue;red', ['red', 'blue']), ('yellow;blue;red', ['red', 'blue', 'yellow'])]:
            with self.subTest(values=values):
                output = self.major(values)
                self.assertEqual(re.findall(r'data-icon-key="state/(red|blue|yellow)"', output), expected)
                self.assertEqual(re.sub(r'\[\[File:[^\]]+\]\]|<[^>]+>|\s+', '', output), '随机加成')
                self.assertNotIn('<br>', output)
                self.assertNotIn('td2-major-option', output)

    def test_simultaneous_is_exact_existing_three_lines(self):
        expected = '<br>'.join(self.wiki.template('TD2主属性显示', {'1': c}) for c in ('red', 'blue', 'yellow'))
        self.assertEqual(self.major('yellow', '是').strip(), expected.strip())
        for value in ('15%', '170,000', '1.0'):
            self.assertIn(value, expected)

    def test_minor_changes_only_wording_and_keeps_icon_and_count(self):
        source = (ROOT / 'wiki/templates/品牌次属性行.wiki').read_text(encoding='utf8')
        old = WikiSubset(ROOT, sources={'wiki/templates/品牌次属性行.wiki': source.replace('内容=随机加成', '内容=随机任意加成')})
        for count in ('1', '2'):
            params = {'数量': count}
            current = self.wiki.template('品牌次属性行', params)
            self.assertEqual(current, old.template('品牌次属性行', params).replace('随机任意加成', '随机加成'))
            self.assertEqual(current.count('data-icon-key="state/random"'), int(count))

    def test_mapped_core_count_and_selection_are_not_tied_to_a_slot(self):
        from tools.equipment.lua import LuaBoundary
        boundary=LuaBoundary(self.wiki);lua=boundary.lua
        entity=lua.eval("require('Module:TD2装备映射')")['entities']['set:4cdce5b25c405137000321f5482f6f7b']
        for selection,count in [('fixed',3),('random',1),('random',2)]:
            entity['rules']['slot:mask']['core']=lua.table_from({'count':count,'selection':selection,'types':['red','blue','yellow']},recursive=True)
            output=boundary.invoke('TD2资料映射','core',{'资料ID':'set:4cdce5b25c405137000321f5482f6f7b','规则':'slot:mask'})
            self.assertEqual(output.count('随机加成'),count if selection=='random' else 0)
            for value in ('15%','170,000','1.0'):self.assertEqual(value in output,selection=='fixed')

    def test_named_core_uses_the_same_mapping(self):
        from tools.equipment.lua import LuaBoundary
        boundary=LuaBoundary(self.wiki);lua=boundary.lua
        entity=lua.eval("require('Module:TD2装备映射')")['entities']['set:4cdce5b25c405137000321f5482f6f7b']
        entity['rules']['named:gear_511_keeper']['core']=lua.table_from({'count':3,'selection':'fixed','types':['red','blue','yellow']},recursive=True)
        self.wiki.lua_boundary=boundary
        raw=(ROOT/'wiki/pages/brands/品牌套装-5.11 Tactical.wiki').read_text('utf8')
        output=self.wiki.expand(raw,{})
        from reader_test_html import nodes
        card=next(n for n in nodes(output,'td2-equipment') if n.attrs.get('id')=='named-gear_511_keeper')
        for value in ('15% 武器伤害','170,000 装甲','1.0 技能分阶'):self.assertIn(value,card.text)


if __name__ == '__main__':
    unittest.main()
