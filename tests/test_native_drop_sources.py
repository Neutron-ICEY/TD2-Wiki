import copy
import unittest
from types import SimpleNamespace
from tools.equipment import native_tree as tree
from tools.equipment.native_drop_sources import permits, targeted, dungeon_drops, CONTEXTS


class NativeDropSourcesTests(unittest.TestCase):
    def test_dungeon_chance_belongs_to_an_exclusive_fixed_roll(self):
        def node(header,body):
            return header+'\n{\n'+body+'\n}\n'
        quality='4CDCE5B25BE6DB97000330865A3EA4FE'
        chart=node('LootQualityChart Exotic < uid='+quality+' >',node('myLootQualityChartList',
            node('LootQualityChartSourceLevel Max','myMinLevel 40\n'+node('myLootQualityChartElementList',
                node('LootQualityChartElement Exotic','myQuality Exotic\nmyDropChance 100')))))
        craft=SimpleNamespace(document=lambda path:tree.parse(chart))
        item=node('LootItem Item',node('myIncludeLootTags','ItemTag Test Drop'))
        group=node('LootGroup Boss','myDropChancePercentage 10\nmyUseQualityUnluckyStreaks FALSE\n'
            +'myQualityChart < uid='+'F'*32+' > = Exotic '+quality+'\n'+node('myLootItemList',item))
        gear={'one':{'obtainable':True,'quality':'Exotic','tags':['Drop']}}
        def roll(groups,objects):
            table=tree.parse(node('LootTable Test',node('myLootGroups',groups)))['children'][0]
            return dungeon_drops(craft,table,objects)
        self.assertEqual(roll(group,gear),{'one':10})
        self.assertEqual(roll(group.replace('Percentage 10','Percentage 0'),gear),{})
        self.assertEqual(roll(group,{**gear,'two':gear['one']}),{'one':None,'two':None})
        self.assertEqual(roll(group+group,gear),{'one':None})
        self.assertEqual(roll(group.replace('UnluckyStreaks FALSE','UnluckyStreaks TRUE'),gear),{'one':None})
        chart=chart.replace('myDropChance 100','myDropChance 20')
        self.assertEqual(roll(group,gear),{'one':None})

    def test_boss_skill_requirement_needs_an_explicit_inventory_state(self):
        condition={'type':'LootConditionHasItem','properties':['myRequiredItemType skill','myIsNegated TRUE']}
        self.assertTrue(permits(condition,{'inventory':{'skill':False}}))
        self.assertFalse(permits(condition,{'inventory':{'skill':True}}))
        with self.assertRaises(KeyError):permits(condition,{'inventory':{}})

    def test_runtime_conditions_validate_all_branches_and_respect_negation(self):
        zone={'type':'LootConditionIsInDarkZone','properties':[],'children':[]}
        outside={**zone,'properties':['myIsNegated TRUE']}
        self.assertFalse(permits(zone,CONTEXTS[0]))
        self.assertTrue(permits(outside,CONTEXTS[0]))
        for bad in [dict(zone,properties=['myFutureMode TRUE']),dict(zone,children=[zone]),dict(zone,type='Unknown')]:
            with self.assertRaises(ValueError):permits({'type':'ORCondition','children':[outside,bad]},CONTEXTS[0])
        bounds={'type':'LootConditionIsLivingWorldSimulationSiteCurrentDefenceLevel','properties':['myIsNegated TRUE','myMinLevel 1','myMaxLevel 4']}
        self.assertTrue(permits(bounds,CONTEXTS[0]))

    def test_targeted_requires_real_list_reference_parent_conditions_and_positive_chance(self):
        generic=tree.parse('''LootGroup Parent
{
 myConditions = Context
 myDropChancePercentage 20
}''')
        definitions=tree.parse('''LootConditions Context
{
 myConditionList
 {
  LootConditionIsInDarkZone Outside
  {
   myIsNegated TRUE
  }
 }
}''')
        table=tree.parse('''LootTable Test
{
 myLootGroups
 {
  LootGroup Drop : Parent
  {
   myLootItemList = Items 00000000000000000000000000000000
  }
 }
}''')['children'][0]
        crafting=SimpleNamespace(document=lambda p:definitions if 'conditionlists/' in p else generic)
        row={'item_list':'Items','conditions':[]}
        rows={'test':copy.deepcopy(row)};targeted(crafting,table,rows)
        self.assertEqual(rows['test']['entry_scope'],'route')
        for change in ('list','chance','condition','parent','zone'):
            altered=copy.deepcopy(table);testrow=copy.deepcopy(row)
            child=altered['children'][0]['children'][0]
            if change=='list':child['properties']=[('myLootItemList = Other 00000000000000000000000000000000',1)]
            if change=='chance':child['properties'].append(('myDropChancePercentage 0',1))
            if change=='condition':testrow['conditions']=[{'type':'Unknown'}]
            if change=='parent':child['header']='LootGroup Drop : Missing'
            if change=='zone':testrow['conditions']=[{'type':'LootConditionIsInDarkZone'}]
            rows={'test':testrow};targeted(crafting,altered,rows)
            self.assertEqual(rows['test']['entry_scope'],'pool',change)
