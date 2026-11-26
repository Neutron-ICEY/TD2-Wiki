import unittest
from exotic_lua_support import ExoticLuaReader, ROOT
from reader_test_html import nodes


class ExoticRandomIconTests(unittest.TestCase):
    def test_acosta_kneepads_uses_offense_then_defense_value_icons(self):
        html=ExoticLuaReader().expand((ROOT/'wiki/pages/exotic-gear/奇特装备-阿科斯塔护膝.wiki').read_text(encoding='utf8'),{})
        rows=[row for row in nodes(html,'td2-equipment-row') if row.find_all('td2-row-label')[0].text=='次属性：']
        self.assertEqual(len(rows),2)
        for row,category in zip(rows,('offense','defense')):
            value=row.find_all('td2-row-value')[0]
            self.assertEqual(value.text,'随机加成')
            self.assertEqual([i.attrs['data-icon-key'] for i in value.find_all('td2-icon')],['attribute_category/'+category])
            self.assertEqual(row.find_all('td2-icon')[0].attrs['data-icon-key'],'equipment_row/minor_attribute')
        self.assertIn('15% 武器伤害', [row.text for row in nodes(html, 'td2-row-value')])

    def test_investor_keeps_mixed_minor_icons_and_random_three_core_icons(self):
        html=ExoticLuaReader().expand((ROOT/'tests/fixtures/exotic-gear/investor.wiki').read_text(encoding='utf8'),{})
        rows=nodes(html,'td2-equipment-row')
        minor=[r.find_all('td2-row-value')[0] for r in rows if r.find_all('td2-row-label')[0].text=='次属性：']
        self.assertEqual(len(minor),3)
        for value in minor:
            self.assertEqual(value.text,'随机加成')
            self.assertEqual([i.attrs['data-icon-key'] for i in value.find_all('td2-icon')],['state/random'])
        major=next(r.find_all('td2-row-value')[0] for r in rows if r.find_all('td2-row-label')[0].text=='主属性：')
        self.assertEqual([i.attrs['data-icon-key'] for i in major.find_all('td2-icon')],['state/red','state/blue','state/yellow'])

    def render_pool(self,categories,missing=False,wrong_kind=False):
        rules=[dict(id='rule_'+str(i),kind='core' if wrong_kind else 'ordinary',**({'category':category} if category is not None else {})) for i,category in enumerate(categories)]
        pool=dict(id='test_pool',kind='ordinary',rules=[r['id'] for r in rules]+(['unknown'] if missing else []))
        reader=ExoticLuaReader(equipment_patch={'attributes':{'rules':rules,'pools':[pool]},'equipment':{'exotic:'+'0'*32:{'fields':{'装备ID':'exotic:'+'0'*32,'装备名称':'NON-GAME-FACT','装备部位':'kneepads','插件槽数':'0'},'slots':[{'槽位ID':'slot_1','类型':'次属性','选择方式':'随机','候选池':'test_pool'}]}}})
        raw='{{奇特装备信息|资料ID=exotic:'+'0'*32+'}}'
        return reader.expand(raw,{})

    def test_single_category_uses_existing_icon_and_mixed_or_missing_category_falls_back(self):
        for categories,key in [(['offense','offense'],'attribute_category/offense'),(['defense','defense'],'attribute_category/defense'),(['utility','utility'],'attribute_category/utility'),(['offense','defense'],'state/random'),(['defense','offense','defense'],'state/random'),(['offense',None],'state/random'),([None],'state/random'),(['unsupported'],'state/random')]:
            with self.subTest(categories=categories):
                html=self.render_pool(categories)
                self.assertNotIn('td2-data-error',html)
                row=nodes(html,'td2-equipment-row')[0]
                value=row.find_all('td2-row-value')[0]
                self.assertEqual(value.text,'随机加成')
                self.assertEqual([i.attrs['data-icon-key'] for i in value.find_all('td2-icon')],[key])

    def test_invalid_pool_members_still_reject_rendering(self):
        self.assertIn('td2-data-error',self.render_pool(['offense'],missing=True))
        self.assertIn('td2-data-error',self.render_pool(['offense'],wrong_kind=True))


if __name__=='__main__':unittest.main()
