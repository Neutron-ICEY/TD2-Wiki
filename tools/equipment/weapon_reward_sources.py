"""Weapon grants at specialization nodes and registered blueprint reward chains."""
import re
from .native_blueprint_rewards import blueprint_index, blueprint_target, grant
from . import native_tree as tree
from .native_sources import LOOT, reference_nodes
from .native_drop_sources import direct_drops, eligible, dungeon_drops, dungeon_label
from .native_special_sources import referenced, reward_difficulties
from .native_source_rules import uid


BASE='hunter/game system data/juice/'


def project(crafting, weapons, blueprints, items=None):
    blueprint_files=blueprint_index(blueprints)
    for name,fn in (('settlement_blueprint',lambda: settlements(crafting,blueprint_files)),
                    ('specialization_rewards',lambda: specializations(crafting,weapons,blueprint_files)),
                    ('summit_rewards',lambda: summit(crafting,weapons,blueprint_files)),
                    ('classified_boss',lambda: classified_bosses(crafting,items if items is not None else weapons)),
                    ('incursion_boss',lambda: incursion_bosses(crafting,items if items is not None else weapons,blueprints))):
        try:fn()
        except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing(name,error)


def settlements(crafting,blueprint_files):
    rows={}
    source=BASE+'projects/projects.juice'
    for p in crafting.document(source)['children']:
        match=re.match(r'Project (Rooftops|Village)_Mil_',p['header'])
        if not match:continue
        ref=tree.reference(tree.prop(p,'myCompletionReward'))
        group_file=BASE+'rewards/'+ref['name'].lower()+'.mreward'
        group=reference_nodes(crafting,group_file,ref['uid'])
        references=tree.child(group,'myRewardReferences')
        if not references:continue
        for value,_ in references['properties']:
            if not value.startswith('RewardItem '):continue
            reward=tree.reference(value[value.index('<'):])
            if not reward['name'].lower().startswith('rwref_blueprint_campaign_'):continue
            reward_file=BASE+'rewards/'+reward['name'].lower()+'.mreward'
            item=reference_nodes(crafting,reward_file,reward['uid'])
            for target in blueprint_target(crafting,blueprint_files,item):
                settlement={'Rooftops':'戏院','Village':'校区'}[match[1]]
                text=settlement+'聚落计划「'+crafting.text(tree.prop(p,'myName'))+'」'
                rows[uid(p)+':'+target]=grant('settlement_blueprint',source,uid(p),target,text,
                    source=reward_file,reward_uid=reward['uid'],group=group_file,group_uid=ref['uid'])
    crafting.unit(['routes','settlement_blueprint'],rows)


def specializations(crafting,weapons,blueprint_files):
    native=crafting.native
    sidearms={};research={}
    folder=BASE+'playerspecializations'
    for file in sorted(native.file(folder).glob('playerspecialization_*.mplayerspecialization')):
        source=file.relative_to(native.root).as_posix()
        spec,=[n for n in crafting.document(source)['children'] if n['header'].startswith('PlayerSpecialization ')]
        spec_name=crafting.text(tree.prop(spec,'myName'))
        elements={}
        for include in native.includes(source):
            if include.endswith('.mplayerspecializationelement'):
                for n in crafting.document(include)['children']:
                    if n['header'].startswith('PlayerSpecializationElementItem '):elements[uid(n)]=(n,include)
        grid=next(n for n in spec['children'] if n['header']=='myElementGridByLevels')
        for cell in tree.walk(grid):
            raw=tree.prop(cell,'myElement')
            if not raw or raw.endswith('NULLREFERENCE'):continue
            element=elements.get(tree.reference(raw)['uid'])
            if not element:continue
            node,element_file=element
            target=tree.reference(tree.prop(node,'myItemType'))['uid']
            if target not in weapons:continue
            level=tree.prop(node,'myRequiredPlayerLevel')
            text=spec_name+'专长解锁配枪'+('（'+level+'级）' if level else '')
            sidearms[uid(node)]=grant('specialization_sidearm',source,uid(node),target,text,
                source=element_file,specialization_uid=uid(spec))
        adventure=tree.prop(spec,'myAdventure','').strip('"')
        if not adventure:continue
        for stage in tree.walk(crafting.document(adventure)):
            if not stage['header'].startswith('AdventureStage '):continue
            normal=tree.child(stage,'myNormalReward')
            reward_file=tree.prop(normal,'myReward','').strip('"') if normal else ''
            if not reward_file:continue
            for group in crafting.document(reward_file)['children']:
                if not group['header'].startswith('RewardGroup '):continue
                rewards=tree.child(group,'myRewards')
                for item in rewards['children'] if rewards else []:
                    if not item['header'].startswith('RewardItem '):continue
                    for target in blueprint_target(crafting,blueprint_files,item):
                        text=spec_name+'实地研究（'+crafting.text(tree.prop(stage,'myName'))+'）'
                        research[uid(stage)+':'+target]=grant('field_research_blueprint',adventure,uid(stage),target,text,
                            source=reward_file,reward_uid=uid(item),specialization=source,specialization_uid=uid(spec))
    crafting.unit(['routes','specialization_sidearm'],sidearms)
    crafting.unit(['routes','field_research_blueprint'],research)



def summit(crafting,weapons,blueprint_files):
    settings=BASE+'mission/skyscrapersettings.juice'
    tiers=BASE+'rewards/tieredrewardsets/tieredrewardset_skyscraperchallengeset.mtieredrewardset'
    config,=[n for n in crafting.document(settings)['children'] if n['header'].startswith('SkyscraperSettings ')]
    reward_set=reference_nodes(crafting,tiers,tree.reference(tree.prop(config,'myChallengeSetsTieredRewardSet'))['uid'])
    rank,=[n for n in tree.child(reward_set,'myNormalTierRewards')['children'] if tree.prop(n,'myScore')=='5']
    normal=reference_nodes(crafting,tiers,tree.reference(tree.prop(rank,'myNormalReward'))['uid'])
    group_file=tree.prop(normal,'myReward').strip('"')
    group,=[n for n in crafting.document(group_file)['children'] if n['header'].startswith('RewardGroup ')]
    reward_file=BASE+'rewards/rwref_summit_challenge exotic_weapon.mreward'
    result={'summit_weapon':{},'summit_blueprint':{}}
    for value,_ in tree.child(group,'myRewardReferences')['properties']:
        if not value.startswith('RewardGroup '):continue
        ref=tree.reference(value[value.index('<'):])
        if ref['name'].strip('"').lower()!='rwref_summit_challenge exotic_weapon':continue
        bundle=reference_nodes(crafting,reward_file,ref['uid'])
        if not reward_difficulties(bundle):continue
        for item in tree.child(bundle,'myRewards')['children']:
            edges=dict(source=reward_file,tiers=tiers,group=group_file,reward_uid=uid(item))
            if item['header'].startswith('RewardItem '):
                kind='summit_blueprint'
                targets=blueprint_target(crafting,blueprint_files,item)
            elif item['header'].startswith('RewardLoot ') and reward_difficulties(item):
                kind='summit_weapon'
                loot=tree.reference(tree.prop(item,'myLootTable'))
                edges['table']=LOOT+loot['name'].lower()+'.mloottable'
                table=reference_nodes(crafting,edges['table'],loot['uid'])
                targets=direct_drops(table,weapons,{})
            else:continue
            for target in targets:
                result[kind][target]=grant(kind,settings,uid(rank),target,'',**edges)
    for kind,rows in result.items():crafting.unit(['routes',kind],rows)



def classified_bosses(crafting,weapons):
    rows={}
    for model in ('mil_boss_ca01_engineer','cul_boss_ca02_flamer','mil_boss_ca03_tank',
                  'bla_boss_ca04_medic','cle_boss_ca05_sniper','cul_boss_ca06_tank'):
        entry=BASE+'ai/npc/'+model+'.mnpc'
        npc,=[n for n in crafting.document(entry)['children'] if tree.prop(n,'myLootTable')]
        if tree.prop(npc,'myLootTable').endswith('= NULLREFERENCE'):continue
        source,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
        for link in tree.walk(table):
            raw=tree.prop(link,'myTable')
            if not raw or not link['header'].startswith('LootTableItem '):continue
            ref=tree.reference(raw)
            if not ref['name'].lower().endswith('_normal'):continue
            context={'difficulty':'Normal'}
            if not eligible(link,table,context):continue
            subfile,subtable=referenced(crafting,raw,'loot/loottables','.mloottable')
            text='机密任务：击败'+crafting.text(tree.prop(npc,'myUIName'))
            for target in direct_drops(subtable,weapons,context):
                rows[uid(npc)+':'+target]=grant('classified_boss',entry,uid(npc),target,text,
                    source=source,table=subfile,table_uid=ref['uid'],difficulty='Normal')
    crafting.unit(['routes','classified_boss'],rows)



def incursion_bosses(crafting,weapons,blueprints):
    groups={'incursion_boss':{},'incursion_blueprint':{}}
    for mission,models,placement in (
        ('ninc01_meret_estate',('ninc01_boss01','ninc01_boss02_alpha','ninc01_boss02_bravo','ninc01_tank_minigun_named'),None),
        ('ninc02_dam',('rik_boss_ninc02_rusher','rik_boss_ninc02_leader_female'),
         'hunter/baked_maps/6eb4a6196788fa4100203f892660fa35/ts[3160,0,2960]_b[0].mbucket.decompiled')):
        origin=BASE+'mission/'+mission+'.mmission'
        config,=[n for n in crafting.document(origin)['children'] if n['header'].startswith('Mission ')]
        activity=crafting.text(tree.prop(config,'myHeadingText')).replace('“','').replace('”','')
        for model in models:
            entry=BASE+'ai/npc/'+model+'.mnpc'
            npc,=[n for n in crafting.document(entry)['children'] if n['header'].startswith('NPC ')]
            if placement and 'UID = #&'+uid(npc)+',' not in crafting.native.file(placement).read_text('utf-8-sig'):
                raise ValueError('Missing incursion boss placement: '+entry)
            source,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
            action='击败'+crafting.text(tree.prop(npc,'myUIName'))
            for target,chance in dungeon_drops(crafting,table,{**weapons,**blueprints}).items():
                kind='incursion_blueprint' if target in blueprints else 'incursion_boss'
                groups[kind][uid(npc)+':'+target]=grant(kind,entry,uid(npc),target,dungeon_label(activity,action,chance),
                    origin=origin,source=source,table_uid=uid(table),drop_percent=chance,**({'placement':placement} if placement else {}))
    for kind,rows in groups.items():crafting.unit(['routes',kind],rows)
