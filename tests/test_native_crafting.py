from tools import identity as identity_catalog
import copy
import json
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from tools.equipment.crafting import bracket_amount, currency_requirement, requirements
from tools.equipment.crafting import Crafting
from tools.equipment.native import Native
from tools.equipment import native_tree as tree
from tools.equipment.native_sources import matches, project as project_sources, PROJECTS

ROOT=Path(__file__).resolve().parents[1]


class NativeCraftingTests(unittest.TestCase):
    def test_missing_source_translation_keeps_identity_and_tag_relationship(self):
        data=tree.parse('''SourceInfo Hint
{
 mySourceText "guid = #AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
 myItemTags
 {
  ItemTag Test Recipe
 }
}''')
        crafting=Crafting(None,ROOT)
        with patch.object(crafting,'document',return_value=data),patch.object(crafting,'text',side_effect=KeyError('missing translation')):
            infos=crafting.source_infos()
        identity='blueprint_source_'+'a'*32
        self.assertEqual(infos[identity]['tags'],['Recipe'])
        self.assertTrue(crafting.unavailable)
        self.assertFalse(any(u['path']==['sources',identity,'text'] for u in crafting.units))

    def test_incomplete_project_reward_scan_cannot_replace_existing_routes(self):
        projects=tree.parse('''Project Test < uid=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA >
{
 ProjectObjectiveActivity Test
 {
  myCompletionReward < uid=CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC > = reward BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
 }
}''')
        reward=tree.parse('''RewardList Test < uid=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB >
{
 RewardItem Test
 {
  myItemTypeFile "hunter/game system data/juice/item/blueprint.mitem"
 }
}''')
        for state in ('complete','missing','invalid'):
            with self.subTest(state=state):
                crafting=Crafting(SimpleNamespace(file=lambda _:SimpleNamespace(is_file=lambda:state!='missing')),ROOT)
                def document(source):
                    if source==PROJECTS:return projects
                    if source.endswith('/reward.mreward') and state!='invalid':return reward
                    raise ValueError('Unavailable fixture')
                with patch.object(crafting,'document',side_effect=document):
                    project_sources(crafting,{}, {'D'*32:{'tags':[]}}, [{'_source':'hunter/game system data/juice/item/blueprint.mitem','resource_uid':'D'*32}])
                groups=[u for u in crafting.units if u['path']==['routes','project_reward']]
                if state=='complete':
                    self.assertEqual(next(iter(groups[0]['value'].values()))['targets'],['D'*32])
                else:
                    self.assertEqual(groups,[])
                    self.assertTrue(any(u['target']=='project_rewards' for u in crafting.unavailable))

    def test_duplicate_native_identity_stops_projection_before_import(self):
        for kind in ('ArmorItem','WeaponItem','CraftingBlueprintItem'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);items=root/'hunter/game system data/juice/item';items.mkdir(parents=True)
                for name in ('first','second'):(items/(name+'.mitem')).write_text(kind+' '+name+' < uid='+'A'*32+' >\n{\n}\n','utf8')
                with self.assertRaisesRegex(RuntimeError,'Duplicate native'):Crafting(Native(root),ROOT).scan()

    def test_currency_power_is_not_item_level_and_brackets_are_discrete(self):
        rows=[dict(A='0',B='2',C='5',min_level='Level1'),dict(A='0',B='0',C='23',min_level='WarlockLevel31')]
        self.assertEqual(bracket_amount(rows,40),23)
        self.assertEqual(bracket_amount(rows,30,power=100),205)
        with self.assertRaisesRegex(ValueError,'power required'):bracket_amount(rows,30)
        with self.assertRaisesRegex(ValueError,'rounding'):bracket_amount([dict(A='0',B='0',C='1.5',min_level='Level1')])
        with self.assertRaisesRegex(ValueError,'progression'):bracket_amount([dict(A='0',B='0',C='1',min_level='FutureTier')])

    def test_nested_tags_are_or_of_and_and_exclusions_are_respected(self):
        node=tree.parse('''LootItem Test
{
 myIncludeLootTags
 {
  ItemTag A First
  LootTagsAND Pair
  {
   ItemTag B Second
   ItemTag C Third
  }
 }
 myExcludeTags
 {
  ItemTag D Excluded
 }
}''')['children'][0]
        self.assertTrue(matches(node,['First']))
        self.assertFalse(matches(node,['Second']))
        self.assertTrue(matches(node,['Second','Third']))
        self.assertFalse(matches(node,['First','Excluded']))

    def test_formula_parser_uses_currency_uid_not_reference_uid_or_label(self):
        node=tree.parse('''CraftingCurrencyRequirement MisleadingName
{
 myCurrencyDefinition < uid=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA > = Actual BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
 myBracketedAmounts
 {
  BracketedCraftingValueFormula ArbitraryLabel
  {
   myC 42.0
   myMinItemLevel WarlockLevel31
  }
 }
}''')['children'][0]
        value=currency_requirement(node)
        self.assertEqual(value['currency_uid'],'B'*32)
        self.assertEqual(bracket_amount(value['brackets']),42)
        renamed=copy.deepcopy(node);renamed['header']='CraftingCurrencyRequirement Renamed'
        self.assertEqual(tree.semantic(node),tree.semantic(renamed))

    def test_costs_add_currency_tags_but_never_guess_bench_quality_or_item_specificity(self):
        cost=lambda amount:{'currency_uid':'A'*32,'brackets':[dict(A='0',B='0',C=str(amount),min_level='Level1')]}
        data={'blueprints':{'B':{'tags':['General','Specific'],'max_level':'40.999','quality_override':None}},
              'crafting_rules':{'General':{'qualities':{'Orange':[cost(8)]}},'Specific':{'qualities':{'Orange':[cost(3)]}}}}
        with self.assertRaisesRegex(ValueError,'bench quality'):requirements(data,'B')
        self.assertEqual(requirements(data,'B','Orange')['currencies'],{'A'*32:11})
        with self.assertRaisesRegex(ValueError,'maximum'):requirements(data,'B','Orange',41)
        data['blueprints']['B']['quality_override']='Orange'
        self.assertEqual(requirements(data,'B','Grey')['profile']['quality'],'Orange')
        data['item_requirements']={'General':{},'Specific':{}}
        with self.assertRaisesRegex(ValueError,'Most-specific'):requirements(data,'B','Orange')

    def test_current_relations_keep_real_variants_conditions_and_unknowns(self):
        data=identity_catalog.read_json(ROOT/'data/equipment/crafting.json')
        b=data['blueprints']['E03CE5EA639B4CAF000367CA5D34E25A']
        self.assertEqual(b['targets'],['F58BDD56638F38F800036B57137F027E'])
        self.assertEqual(data['items'][b['targets'][0]]['kind'],'named')
        random=[b for b in data['blueprints'].values() if b['random']]
        self.assertEqual(len(random),6)
        self.assertIn('4CDCE5B25B97DC790002A1AFCBA5ED10',{t for b in random for t in b['targets']})
        self.assertEqual(len(data['routes']['reconstructed_cache']),1)
        cache=next(iter(data['routes']['reconstructed_cache'].values()))
        weapon_blueprints=[t for t in cache['targets'] if data['blueprints'][t]['category']=='Weapon']
        self.assertEqual(len(cache['targets'])-len(weapon_blueprints),60)
        self.assertEqual(len(weapon_blueprints),75)
        self.assertTrue(data['routes']['project_reward'])
        self.assertTrue(any(r['conditions']['group'] for r in data['routes']['vendor'].values()))
        self.assertTrue(all(r['verification']=='native_only' for routes in data['routes'].values() for r in routes.values()))
        self.assertNotIn('4CDCE5B25B98D5C40002A3443B0038F0',data['blueprints'])


if __name__=='__main__':unittest.main()
