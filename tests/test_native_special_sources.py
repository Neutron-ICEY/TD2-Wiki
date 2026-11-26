import unittest
from unittest.mock import patch
from pathlib import Path
from tools.equipment.crafting import Crafting
from tools.equipment import native_special_sources as special, native_tree as tree
from tools.equipment.native_sources import reference_nodes
from tools.equipment.native_blueprint_rewards import project_window


def block(header,body=''):
    return header+'\n{\n'+body+'\n}\n'


class SpecialSourceTests(unittest.TestCase):
    def test_project_reward_window_uses_the_offset_and_ends_with_the_parent_schedule(self):
        schedule_uid='0AF8F42D66A1543200036DE3712ADF3D'
        event=block('GameScheduleEntryProject test')
        slot=block('OffsetGameScheduleManualEntry child','myGameSchedule '+schedule_uid+'\n'
            +'myOffset 2\nmyDuration 8\nmyTimeUnit Days\n'+block('myEntries',event))
        season='myActiveTime "2026-11-01 08:00:00 to 2026-11-05 07:59:59"\n'
        schedule=tree.parse(block('GameScheduleManualEntry parent',season+block('myOffsetManualEntries',slot)))
        target=next(n for n in tree.walk(schedule) if n['header'].startswith('GameScheduleEntryProject '))
        craft=Crafting(None,Path(__file__).resolve().parents[1])
        pool=tree.parse(block('GameSchedule projects < uid='+schedule_uid+' >'))
        with patch.object(craft,'document',return_value=pool):
            self.assertEqual(project_window(craft,schedule,target),'"2026-11-03 08:00:00 to 2026-11-05 07:59:59"')

    def test_mission_prerequisites_reject_unknown_types_and_missing_references(self):
        craft=Crafting(None,Path(__file__).resolve().parents[1])
        with self.assertRaisesRegex(ValueError,'inherited conditions'):special.mission_requirements(craft,tree.parse(block('Mission Test'))['children'][0])
        for child in [block('UnknownPrerequisite Test'),block('PlayerRequiredLevelPrerequisite Test','myRequiredLevel 99'),
                      block('MissionIsStoryCompletedPrerequisite Test','myMission < uid='+'A'*32+' > = missing '+'B'*32)]:
            node=tree.parse(block('Mission Test',block('myPrerequisites',child)))['children'][0]
            with patch.object(craft,'document',return_value=tree.parse('')),self.assertRaises(ValueError):special.mission_requirements(craft,node)

    def test_reward_gates_and_teasers(self):
        def node(body):return tree.parse(block('RewardLoot Test',body))['children'][0]
        self.assertEqual(special.reward_difficulties(node('')),set(special.DIFFICULTIES))
        self.assertEqual(special.reward_difficulties(node('myIsRewardUsedAsTeaser TRUE')),set())
        self.assertEqual(special.reward_difficulties(node('myIncludedInPreview FALSE')),set(special.DIFFICULTIES))
        self.assertEqual(special.reward_difficulties(node(block('myValidMissionDifficulties','MissionDifficulty Test Hard'))),{'Hard'})
        for body in ['myRequiresLegendaryCompletion TRUE','myUnknownGate TRUE','myIsRewardUsedAsTeaser INVALID',
                     block('myValidMissionDifficulties','MissionDifficulty Test Unknown'),block('myConditions')]:
            with self.subTest(body=body),self.assertRaises(ValueError):special.reward_difficulties(node(body))

    def test_runtime_unknown_conditions_and_global_difficulty_defaults(self):
        def row(kind,props=()):return {'conditions':[{'type':kind,'properties':list(props),'children':[]}]}
        rows={'default':row('LootConditionGlobalDifficulty'),'hard':row('LootConditionGlobalDifficulty',['myGlobalDifficulty Hard']),
              'unknown':row('NewCondition'),'not_normal':row('LootConditionGlobalDifficulty',['myOperator NotEqual']),
              'operator':row('LootConditionGlobalDifficulty',['myOperator UnknownComparison']),
              'contradiction':{'conditions':[row('LootConditionIsMissionDifficulty',['myMissionDifficulty Hard'])['conditions'][0],row('LootConditionIsMissionDifficulty',['myMissionDifficulty Heroic'])['conditions'][0]]}}
        special.runtime(rows,['Normal','Hard'])
        self.assertEqual(rows['default']['runtime_witnesses'][0]['global_difficulty'],'Normal')
        self.assertEqual(rows['hard']['runtime_witnesses'][0]['global_difficulty'],'Hard')
        self.assertEqual([w['global_difficulty'] for w in rows['not_normal']['runtime_witnesses']],['Hard'])
        self.assertTrue(all(rows[k]['entry_scope']=='pool' for k in ['unknown','operator','contradiction']))

    def test_mission_reference_chain_requires_exact_uids_and_actual_loot(self):
        ids=['A'*32,'B'*32,'C'*32,'D'*32]
        entry=special.JUICE+'mission/test.mmission';group=special.JUICE+'rewards/group.mreward'
        leaf=special.JUICE+'rewards/leaf.mreward';table=special.LOOT+'pool.mloottable'
        ref=lambda name,identity:'< uid='+'F'*32+' > = '+name+' '+identity
        texts={entry:block('Mission test < uid='+ids[0]+' >','myReward '+ref('group',ids[1])+'\n'+block('myPrerequisites')),
               group:block('RewardGroup group < uid='+ids[1]+' >',block('myRewardReferences','RewardLoot "Test label" '+ref('leaf',ids[2]))),
               leaf:block('RewardLoot leaf < uid='+ids[2]+' >','myLootTable '+ref('pool',ids[3])),
               table:block('LootTable pool < uid='+ids[3]+' >')}
        craft=Crafting(None,Path(__file__).resolve().parents[1])
        collect=lambda *args,**kwargs:{'test':{'conditions':[],'targets':['E'*32]}}
        with patch.object(craft,'document',side_effect=lambda f:tree.parse(texts[f])):
            rows=special.mission(craft,collect,'test','test',ids[0],ids[2])
            self.assertEqual(rows['test']['entry_scope'],'route')
            texts[leaf]=texts[leaf].replace('myLootTable','myIsRewardUsedAsTeaser TRUE\nmyLootTable')
            self.assertEqual(special.mission(craft,collect,'test','test',ids[0],ids[2])['test']['entry_scope'],'pool')
            texts[table]=texts[table].replace(ids[3],'0'*32)
            with self.assertRaisesRegex(ValueError,'route UID'):special.mission(craft,collect,'test','test',ids[0],ids[2])
            with self.assertRaisesRegex(ValueError,'route UID'):reference_nodes(craft,entry,'0'*32)


if __name__=='__main__':unittest.main()
