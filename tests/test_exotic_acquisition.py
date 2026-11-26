import unittest
from pathlib import Path
from exotic_lua_support import ExoticLuaReader
from reader_test_html import nodes
ROOT=Path(__file__).resolve().parents[1]
ID='exotic:4cdce5b25d5518e40003409a83b246b0'

class ExoticAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.raw=(ROOT/'tests/fixtures/exotic-gear/coyote.wiki').read_text('utf8')
    def render(self,facts,**fields):
        reader=ExoticLuaReader(acquisition_patch={ID:facts})
        params=''.join('\n|'+k+'='+v for k,v in fields.items())
        return reader.expand(self.raw.replace('{{奇特装备信息','{{奇特装备信息'+params,1),{})
    def test_unknown_source_and_absent_blueprint_are_distinct(self):
        facts={'equipment':[],'blueprint':[],'hasBlueprint':True}
        result=self.render(facts)
        self.assertEqual([n.text for n in nodes(result,'td2-acquisition-result')],['暂无获取资料','暂无获取资料'])
        facts['hasBlueprint']=False
        self.assertEqual([n.text for n in nodes(self.render(facts),'td2-acquisition-result')],['无制作图纸','暂无获取资料'])
    def test_multiple_effective_sources_are_independent(self):
        facts={'equipment':[{'category':'cache','text':'TEST 路线甲；仅甲的前置条件'},{'category':'special','text':'TEST 路线乙'}],'blueprint':[{'category':'vendor','text':'TEST 图纸'}],'hasBlueprint':True}
        result=self.render(facts)
        values=[n.text for n in nodes(result,'td2-acquisition-result')]
        self.assertEqual(len(values),2)
        self.assertEqual(values[0],'TEST 图纸');self.assertNotIn('仅甲',values[0])
        for text in ['路线甲','仅甲的前置条件','路线乙']:self.assertIn(text,values[1])
        self.assertNotIn('&amp;amp;',result)
        self.assertNotIn('td2-data-error',result)
    def test_retired_flags_do_not_create_effective_routes(self):
        result=self.render({'equipment':[],'blueprint':[],'hasBlueprint':True},常规获取='是',暗区限定获取='是',装备获取来源='unknown')
        self.assertEqual([n.text for n in nodes(result,'td2-acquisition-result')],['暂无获取资料','暂无获取资料'])
