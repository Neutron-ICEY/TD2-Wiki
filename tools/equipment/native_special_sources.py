"""Registered activity, container, NPC and mission entry chains."""
from functools import lru_cache
import json
import re
from . import native_tree as tree
from .crafting import CATALOG, item_tags, scalar
from .native_sources import LOOT, reference_nodes
from .native_drop_sources import direct_drops, drop_branches, permits, dungeon_drops, dungeon_label
from .native_source_rules import uid

JUICE='hunter/game system data/juice/'
GUARDIANS={
    'alpha':'C54B7AE269BC0BAE00066601348748E8',
    'bravo':'C54B7AE269BC0BED000667E3A2D9EC37',
    'charlie':'C54B7AE269BC0C19000669C7D8835451',
    'delta':'C54B7AE269BC0C4800066BACA653EA82',
    'echo':'C54B7AE269BD51B70003E8A1F8128C9D',
}
DIFFICULTIES=('Story','Normal','Hard','Challenge','Heroic','Legendary')


def referenced(crafting, raw, directory, suffix):
    ref=list_reference(raw)
    source=JUICE+directory+'/'+ref['name'].strip('"').lower()+suffix
    return source,reference_nodes(crafting,source,ref['uid'])


def list_reference(raw):
    # List entries include a type and editor label before the reference value.
    return tree.reference((raw or '')[(raw or '').find('<'):])


def entry_context(node,*members):
    value=tree.semantic(node)
    value['children']=[tree.semantic(n) for n in node['children'] if n['header'] in members]
    return value


def mission_requirements(crafting,node):
    requirements=tree.child(node,'myPrerequisites')
    if requirements is None:raise ValueError('Mission prerequisites unavailable; inherited conditions require review')
    if requirements['properties']:raise ValueError('Unresolved mission prerequisites')
    for child in requirements['children']:
        kind=child['header'].split()[0]
        if child['children'] or len(child['properties'])!=1:raise ValueError('Unresolved mission prerequisite')
        if kind=='MissionIsStoryCompletedPrerequisite':
            referenced(crafting,tree.prop(child,'myMission'),'mission','.mmission')
        elif kind=='PlayerRequiredLevelPrerequisite':
            level=tree.prop(child,'myRequiredLevel','')
            if not level.isdigit() or not 1<=int(level)<=40:raise ValueError('Unresolved mission level')
        else:raise ValueError('Unresolved mission prerequisite: '+kind)


def runtime(rows, difficulties, **context):
    for row in rows.values():
        row['entry_scope']='pool'
        witnesses=[]
        for difficulty in difficulties:
            candidate=dict(context,difficulty=difficulty,global_difficulty=difficulty)
            try:
                if all(permits(c,candidate) for c in row['conditions']):witnesses.append(candidate)
            except (ValueError,KeyError):pass
        if witnesses:
            row['entry_scope']='route';row['runtime_witnesses']=witnesses


def reward_difficulties(node):
    # Reward defaults are defined in rewards.fruit. Unknown gates must not
    # silently become unconditional rewards; myIncludedInPreview is UI-only.
    allowed={'myIncludedInPreview','myDisplayItemTypesInPreview','myRewardHighlightType','myLootTable','mySourceType',
             'mySendToMailboxIfInventoryIsFull'}
    defaults={'myRewardOnce':'FALSE','myRewardOnceForAllValidDifficulties':'FALSE',
              'myRewardOncePerWeeklyInvasion':'FALSE','myRewardWeeklyInvasionReplay':'FALSE',
              'myRewardOncePerBounty':'FALSE','myIsHardcoreModeOnly':'FALSE',
              'myRequiresLegendaryCompletion':'FALSE','myRequiredLevelCategory':'AnyLevel',
              'myRequiredInvasionState':'Any','myRequiredImmersionCharacterState':'NonImmersion',
              'myRewardInterval':'None'}
    if tree.prop(node,'myIsRewardUsedAsTeaser','FALSE')=='TRUE':return set()
    for raw,_ in node['properties']:
        key=raw.split(' ',1)[0]
        if key=='myIsRewardUsedAsTeaser':
            if tree.prop(node,key)!='FALSE':raise ValueError('Invalid teaser flag')
        elif key in defaults:
            if key=='myRequiredImmersionCharacterState' and tree.prop(node,key)=='Any':continue
            if tree.prop(node,key)!=defaults[key]:raise ValueError('Unresolved reward gate: '+key)
        elif key not in allowed:raise ValueError('Unresolved reward property: '+key)
    for child in node['children']:
        if child['header'] not in ('myRewards','myRewardReferences','myValidMissionDifficulties'):
            raise ValueError('Unresolved reward block: '+child['header'])
    valid=tree.child(node,'myValidMissionDifficulties')
    values={p.rsplit(' ',1)[-1] for p,_ in valid['properties']} if valid else set()
    if valid and (valid['children'] or any(not p.startswith('MissionDifficulty ') for p,_ in valid['properties'])):
        raise ValueError('Invalid reward difficulties')
    if not values<=set(DIFFICULTIES):raise ValueError('Unknown reward difficulty')
    return values or set(DIFFICULTIES)


def grants_loot(crafting,group_ref,leaf_uid,difficulty=None):
    source,group=referenced(crafting,group_ref,'rewards','.mreward')
    if not group['header'].startswith('RewardGroup ') or ' : ' in group['header']:
        raise ValueError('Unresolved blueprint reward group: '+source)
    valid=reward_difficulties(group)
    required={difficulty} if difficulty else set(DIFFICULTIES)
    if not required<=valid:return None
    refs=tree.child(group,'myRewardReferences')
    if refs and any(p.startswith('RewardLoot ') and list_reference(p)['uid']==leaf_uid for p,_ in refs['properties']):
        return {'group':source,'group_uid':uid(group)}
    return None


def blueprint_triggers(crafting,reward_uid,*,control_point):
    if control_point:
        source=JUICE+'livingworldsimulation/livingworldsimulationsettings.juice'
        settings,=[n for n in crafting.document(source)['children'] if n['header'].startswith('LivingWorldSimulationSettings ')]
        defence=tree.child(settings,'mySiteDefenceLevels')
        witnesses=[]
        for level,node in enumerate(defence['children']):
            if node['header']!=f'LivingWorldSimulationSiteDefenceLevel "Level {level}"':
                raise ValueError('Unknown control point defence level')
            difficulty=tree.prop(node,'myMissionDifficulty','Normal')
            groups=[grants_loot(crafting,ref,reward_uid,difficulty) for ref,_ in node['properties']
                    if ref.split()[0].endswith('Reward')]
            if groups and all(groups):
                witnesses.append({'settings':source,'level':level,'difficulty':difficulty,'groups':groups})
        levels=[w['level'] for w in witnesses]
        if not levels:return '',[]
        if len(levels)>1 and levels==list(range(levels[0],len(defence['children']))):
            return f'接管警戒等级{levels[0]}以上的控制点',witnesses
        return '接管警戒等级'+'或'.join(str(level) for level in levels)+'的控制点',witnesses

    source=JUICE+'scheduling/projects_boo_dcp_schedule.mgameschedule'
    schedule=reference_nodes(crafting,source,'B3CF2E925CAC525700032A3ED0E56006')
    settings=tree.child(schedule,'myPoolSettings')
    cadence=tree.child(settings,'myPoolCadence')['children']
    if int(tree.prop(schedule,'myNumberOfEntriesToSelect','0'))<1 or not any(n['header'].startswith('GameScheduleCadenceWeekly ') for n in cadence):
        return '',[]
    pool_file,pool=referenced(crafting,tree.prop(settings,'myPool'),'scheduling','.mgameschedulepool')
    project_file=JUICE+'projects/projects.juice'
    for row in tree.child(pool,'myEntries')['children']:
        if not row['header'].startswith('GameScheduleEntryProject ') or row['children'] or len(row['properties'])!=1:continue
        ref=tree.reference(tree.prop(row,'myProject'))
        project=reference_nodes(crafting,project_file,ref['uid'])
        grant=grants_loot(crafting,tree.prop(project,'myCompletionReward'),reward_uid)
        if grant:
            return '完成计划',[dict(grant,schedule=source,
                pool=pool_file,pool_uid=uid(pool),project=project_file,project_uid=ref['uid'])]
    return '',[]


def summit_challenge_grants(crafting, reward_uid, pool_rows):
    settings = JUICE+'mission/skyscrapersettings.juice'
    config, = [n for n in crafting.document(settings)['children'] if n['header'].startswith('SkyscraperSettings ')]
    tiers, rewards = referenced(crafting, tree.prop(config, 'myChallengeSetsTieredRewardSet'), 'rewards/tieredrewardsets', '.mtieredrewardset')
    witnesses = []
    for rank in tree.child(rewards, 'myNormalTierRewards')['children']:
        payout = reference_nodes(crafting, tiers, list_reference(tree.prop(rank, 'myNormalReward'))['uid'])
        group_file = tree.prop(payout, 'myReward').strip('"')
        group, = [n for n in crafting.document(group_file)['children'] if n['header'].startswith('RewardGroup ')]
        refs = tree.child(group, 'myRewardReferences') or {}
        if any(raw.startswith('RewardLoot ') and list_reference(raw)['uid'] == reward_uid for raw,_ in refs.get('properties', [])):
            if reward_difficulties(group) == set(DIFFICULTIES):
                witnesses.append(dict(rank=int(tree.prop(rank, 'myScore')), reward=group_file, reward_group_uid=uid(group)))
    rows = {}
    if witnesses:
        for key,row in pool_rows.items():
            rows[key.replace('blueprint_reward_pool:', 'summit_challenge_blueprint:', 1)] = dict(row,
                kind='summit_challenge_blueprint', entry=tiers, entry_uid=uid(rewards), origin=settings,
                reward=row['entry'], reward_uid=reward_uid, entry_scope='route', text='高峰大厦挑战奖励', display_text='完成高峰大厦挑战',
                runtime_witnesses=witnesses)
    return rows


def mission(crafting,collect,kind,filename,entry_uid,leaf_uid,climax=None):
    entry=JUICE+'mission/'+filename+'.mmission'
    mission_node=reference_nodes(crafting,entry,entry_uid)
    mission_requirements(crafting,mission_node)
    context={entry:entry_context(mission_node,'myPrerequisites','myPrimeTargetClimaxDataList')}
    reward_parent=mission_node
    if climax:
        source,identity,playlist,playlist_uid=climax
        links=tree.child(mission_node,'myPrimeTargetClimaxDataList')
        if not links or not any(list_reference(p)['uid']==identity for p,_ in links['properties']):
            raise ValueError('Climax missing from mission')
        reward_parent=reference_nodes(crafting,source,identity)
        activity_root=reference_nodes(crafting,playlist,playlist_uid)
        activities=[n for n in tree.walk(activity_root) if n['header'].startswith('PrimeTargetCampaignActivityMission ')
                    and tree.prop(n,'myMission') and tree.prop(n,'myPrimeTargetClimaxData')
                    and tree.reference(tree.prop(n,'myMission'))['uid']==entry_uid
                    and tree.reference(tree.prop(n,'myPrimeTargetClimaxData'))['uid']==identity]
        if len(activities)!=1:raise ValueError('Climax activity entry changed')
        context.update({source:entry_context(reward_parent),playlist:tree.semantic(activities[0])})
    group_source,group=referenced(crafting,tree.prop(reward_parent,'myRewardOverride' if climax else 'myReward'),'rewards','.mreward')
    if not group['header'].startswith('RewardGroup ') or ' : ' in group['header']:
        raise ValueError('Unresolved reward group')
    context[group_source]=tree.semantic(group)
    # Follow only the registered reward edge. Other rewards in the mission do
    # not establish this source, especially RewardItem UI teasers.
    local=tree.child(group,'myRewards')
    leaves=[n for n in (local or {'children':[]})['children'] if ('uid='+leaf_uid+' >') in n['header']]
    references=tree.child(group,'myRewardReferences')
    refs=[p for p,_ in (references or {'properties':[]})['properties'] if list_reference(p)['uid']==leaf_uid]
    if len(leaves)+len(refs)!=1:raise ValueError('Reward edge missing or ambiguous')
    if refs:
        leaf_source,leaf=referenced(crafting,refs[0],'rewards','.mreward')
        context[leaf_source]=tree.semantic(leaf)
    else:leaf=leaves[0]
    if not leaf['header'].startswith('RewardLoot ') or ' : ' in leaf['header']:
        raise ValueError('Expected actual RewardLoot')
    difficulties=reward_difficulties(group)&reward_difficulties(leaf)
    table_source,table=referenced(crafting,tree.prop(leaf,'myLootTable'),'loot/loottables','.mloottable')
    rows=collect(kind,table_source,entry,entry_uid,scope=table['header'],strict=True)
    context[table_source]=tree.semantic(table)
    runtime(rows,sorted(difficulties),immersion=False)
    for row in rows.values():row['context_refs']=list(context)
    crafting.unit(['source_contexts',kind],context)
    return rows


def seasonal_cache_files(crafting):
    folder=crafting.native.file(JUICE+'item')
    pattern=re.compile(r'sealed_cache_(?:bp_extension_y\d+s\d+(?:_\w+)?_items|\w+_event_y\d+s\d+)')
    files={f for f in folder.glob('sealed_cache_*.mitem') if pattern.fullmatch(f.stem)}
    previous=json.loads((crafting.root/CATALOG).read_text('utf8'))['routes'].get('season_weapon_cache',{})
    files.update(crafting.native.file(r['entry']) for r in previous.values())
    if not files:raise ValueError('Season cache definitions unavailable')
    return sorted(files)


def season_caches(crafting,items,supports_prototype):
    kind='season_weapon_cache'
    rows={}
    context={'level':40}
    event_names={'sealed_cache_sandstorm_event_y8s2':'沙尘暴','sealed_cache_red_moon_uprising_event_y8s3':'红月肆虐'}
    for file in seasonal_cache_files(crafting):
        entry=file.relative_to(crafting.native.root).as_posix()
        cache,=[n for n in crafting.document(entry)['children'] if n['header'].startswith('BundleItem ')]
        season=re.search(r'_y(\d+)s(\d+)',file.stem)
        label=event_names.get(file.stem,'Y'+season[1]+'S'+season[2])
        cache_name=crafting.text(tree.prop(cache,'myUIName'))+'（'+label+'）'
        tables=tree.child(cache,'myLootTables')
        if not tables:raise ValueError('Cache loot tables unavailable: '+entry)
        for slot in tables['children']:
            if slot['header']!='BundleLootTable "Guaranteed Drop"' or slot['children'] or len(slot['properties'])!=1:continue
            source,table=referenced(crafting,tree.prop(slot,'myLootTable'),'loot/loottables','.mloottable')
            pools=[(source,table)]
            for _,branch in drop_branches(table,'LootTableItem',context):
                pools.append(referenced(crafting,tree.prop(branch,'myTable'),'loot/loottables','.mloottable'))
            for item_source,item_table in pools:
                targets=direct_drops(item_table,items,context,supports_prototype=supports_prototype)
                if targets:
                    rows[uid(cache)+':'+uid(item_table)]=dict(kind=kind,entry=entry,entry_uid=uid(cache),
                        source=source,table=item_source,table_uid=uid(item_table),targets=sorted(targets),
                        display_text=cache_name,level=40,verification='native_only')
    crafting.unit(['routes',kind],rows)


def raid_caches(crafting,items,blueprints):
    rows={}
    for suffix,entry_uid,key_uid,activity,mission_uid,bucket in (
        ('inc01','2736B3655C07B348000364EE50666005','2736B3655C07AB6C00037DCB9AF70BB1','黑暗时刻行动',None,
         '88302af65b0290db0010aa5aa6a35c87/t[480,0,520]_b[0]_[88302af65b0569180000ab1d54441ee8]'),
        ('inc02','2736B3655D10C81D0004037304110E63','2736B3655D1C66250004DF9016341B22','铁驹行动',None,
         '88302af65b0290db0010aa5aa6a35c87/t[-1160,0,1040]_b[0]_[2736b3655ddba4180006ccd4c5b9f191]'),
        ('ninc01','F53BCD9764361C4D00045B85C7B54769','F53BCD9764462B490004C0956A339719','失乐园',
         'F53BCD9762DFB7B40003C13A7664703A','1f8429c85c6d41550005961686308fe5/t[-3600,0,3480]_b[0]'),
        ('ninc02_dam','FBD81EA76A2034F900154CB7DE21FBD3','40EFA9D569CD0BBF00076A12DCEDE2DB','破雨行动',
         'FBD81EA76978BCDD0003DA9A235F598A','6eb4a6196788fa4100203f892660fa35/t[3200,40,2960]_b[0]')):
        placement='hunter/baked_maps/'+bucket+'.mbucket.decompiled'
        interaction='hunter/interaction/sets/interact_loot_table_'+suffix+'_normal_set.propinteraction'
        if f'interactionSetup = "{interaction}"' not in crafting.native.file(placement).read_text('utf-8-sig'):
            raise ValueError('Missing reward crate placement: '+interaction)
        setup,=[n for n in tree.walk(crafting.document(interaction)) if n['header'].startswith('StandardInteraction ')]
        if tree.reference(tree.prop(setup,'myInteractionSettings'))['uid']!=entry_uid:
            raise ValueError('Raid crate interaction changed')
        source='hunter/interaction/settings/interact_loot_table_'+suffix+'_normal.minteractionsetup'
        entry=reference_nodes(crafting,source,entry_uid)
        blocks={n['header'].split()[0]:n for n in entry['children']}
        if tree.prop(blocks['mySetup'],'myPropInteractionType')!='LootCrate':raise ValueError('Expected reward crate')
        requirements=blocks['myRequirements']
        resources=tree.child(requirements,'myResourcesRequired')
        mission_refs=set()
        for gate in requirements['children']:
            if gate is resources or not gate['properties'] and not gate['children']:continue
            if gate['header'] not in ('myRequiredMissions','myRequiredMissionStatuses') or gate['properties']:
                raise ValueError('Unknown crate requirement')
            for condition in gate['children']:
                if condition['children'] or len(condition['properties'])!=1:raise ValueError('Unknown crate mission condition')
                mission_ref=tree.prop(condition,'myMission')
                mission_file,mission=referenced(crafting,mission_ref,'mission','.mmission')
                if not condition['header'].startswith(('CompletedMissionRequirement ','MissionStatusRequirement ')) or uid(mission)!=mission_uid:
                    raise ValueError('Raid crate mission requirement changed')
                mission_refs.add(mission_file)
        cost,=resources['children']
        amount=int(tree.prop(cost,'myAmount'))
        if resources['header']!='myResourcesRequired' or tree.reference(tree.prop(cost,'myCurrency'))['uid']!=key_uid or amount<1:
            raise ValueError('Raid crate key requirement changed')
        table_file,table=referenced(crafting,tree.prop(blocks['myRewardSettings'],'myLootTable'),'loot/loottables','.mloottable')
        for target,chance in dungeon_drops(crafting,table,{**items,**blueprints}).items():
            if target not in items:continue
            rows[entry_uid+':'+target]=dict(kind='raid_cache',entry=source,entry_uid=entry_uid,source=table_file,table_uid=uid(table),
                placement=placement,interaction=interaction,key_uid=key_uid,amount=amount,missions=sorted(mission_refs),
                targets=[target],verification='native_only',drop_percent=chance,
                display_text=dungeon_label(activity,'开启最终奖励箱',chance))
    crafting.unit(['routes','raid_cache'],rows)


def boss_drops(crafting,items):
    rows={}
    missions={'end_dronehelicopter_mm42_vir':('mm42_armyterminal','652ef1c85a8ab28500006f35799c8627/ts[-1880,0,-1040]_b[0]_[2e54428464ae559f000719820d9a1934]'),
              'rog_boss_bravo_rogueagent':('mm32_lowline','4af94da95cc6e4e6000364bc764fca95/ts[-40,-40,600]_b[0]'),
              'rog_boss_delta_rogueagent':('mm31_tombs','4af94da95cc6e4e6000364bc764fca95/ts[680,0,840]_b[0]')}
    skill_requirements={
        'rog_boss_bravo_rogueagent':('s_mod_trap_shock','F09921C85DCC260F00036A89F2C9659D'),
        'rog_boss_delta_rogueagent':('s_mod_decoy_distraction','D9F412CE5DA6C3EE0003629414A433FA')}
    for filename,identity in (
        ('udg_cle_engineer_boss_vir_c','16E4ACB767AB6DA200090E96FFFA7326'),
        ('end_dronehelicopter_mm42_vir','A21C7E1F66D97A7A0005ABAB4A8F568C'),
        ('rog_boss_bravo_rogueagent','96C6A7A35DA6F47600038ED64212B2C7'),
        ('rog_boss_delta_rogueagent','96C6A7A35DA6F57600039805B2F81E12'),
        ('hun_hunter_y8s3_a','F966A4EA6ABE446C00037F13F727E52D')):
        entry=JUICE+'ai/npc/'+filename+'.mnpc'
        npc=reference_nodes(crafting,entry,identity)
        placement=None
        encounter_gates=[]
        if filename in missions:
            mission_file,bucket=missions[filename]
            placement='hunter/baked_maps/'+bucket+'.mbucket.decompiled'
            origin=JUICE+'mission/'+mission_file+'.mmission'
            bound=any(tree.prop(n,'myNPCConfig','').strip('"')==entry for n in tree.walk(crafting.document(origin)))
            bound=bound and ('UID = #&'+identity+',') in crafting.native.file(placement).read_text('utf-8-sig')
            availability='permanent' if bound else 'unresolved'
        elif filename=='udg_cle_engineer_boss_vir_c':
            origin=JUICE+'underground/underground.juice'
            bound=any(tree.prop(n,'myNPC','').endswith(' '+identity) for n in tree.walk(crafting.document(origin)))
            availability='permanent' if bound else 'unresolved'
        else:
            origin=JUICE+'livingworldencounter/livingworldencounters.mlivingworldencounter'
            encounters=[n for n in crafting.document(origin)['children'] if any(
                p.endswith(' '+identity) for sub in tree.walk(n) for p,_ in sub['properties'])]
            for encounter in encounters:
                gate=dict(encounter_uid=uid(encounter),currency=tree.prop(encounter,'myRequiredCurrencyUID',''),
                    amount=int(tree.prop(encounter,'myNumRequiredCurrency','0')),
                    conditions=[tree.prop(n,'myCondition') for n in tree.walk(encounter) if tree.prop(n,'myCondition')])
                encounter_gates.append(gate)
            limited=encounter_gates and all('World.IsHalloween' in g['conditions'] and g['amount']>0
                and g['currency'].endswith(' 61A9E8DE699489720003740FAAF867FE') for g in encounter_gates)
            availability='limited' if limited else 'unresolved'
        table_file,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
        boss='击败'+crafting.text(tree.prop(npc,'myUIName'))
        skill=skill_requirements.get(filename)
        if skill:
            skill_file=JUICE+'item/'+skill[0]+'.mitem'
            mod=reference_nodes(crafting,skill_file,skill[1])
            skill_name=crafting.text(tree.prop(mod,'myUIName'))
        for difficulty in DIFFICULTIES:
            context={'difficulty':difficulty}
            ordinary=direct_drops(table,items,context)
            outcomes=[(ordinary,boss,context)]
            if skill:
                condition={**context,'inventory':{skill[0]:False}}
                extra=direct_drops(table,items,condition)-ordinary
                outcomes.append((extra,'尚未获得「'+skill_name+'」时'+boss,{**condition,'item_source':skill_file,'item_uid':skill[1]}))
            for targets,label,witness in outcomes:
                if targets:
                    key=identity+':'+difficulty+(':inventory' if 'inventory' in witness else '')
                    rows[key]=dict(kind='boss_drop',entry=entry,entry_uid=identity,source=table_file,table_uid=uid(table),
                        targets=sorted(targets),runtime_witnesses=[witness],difficulty=difficulty,origin=origin,
                        availability=availability,placement=placement,verification='native_only',display_text=label)
                    if encounter_gates:rows[key]['encounter_gates']=encounter_gates
    crafting.unit(['routes','boss_drop'],rows)


def mission_items(crafting,items):
    rows={}
    for namespace,name,identity in [('rogue','mm15_capitol','A0FB99F459799B350000366FAEB026FC'),
                                    ('hunter','mm35_statue_of_liberty','5151931C5D667DFE0006104BECD79326')]:
        entry=namespace+'/game system data/juice/mission/'+name+'.mmission'
        mission=reference_nodes(crafting,entry,identity)
        source,group=referenced(crafting,tree.prop(mission,'myReward'),'rewards','.mreward')
        if reward_difficulties(group)!=set(DIFFICULTIES):continue
        title=crafting.text(tree.prop(tree.child(mission,'myReplayExtraData'),'myHeadingText'))
        for reward in (tree.child(group,'myRewards') or {}).get('children',[]):
            if not reward['header'].startswith('RewardLoot ') or tree.prop(reward,'myRewardOnce')!='TRUE':continue
            if reward['children'] or any(p.split(' ',1)[0] not in ('myRewardOnce','mySourceType','myIncludedInPreview','myLootTable') for p,_ in reward['properties']):continue
            table_file,table=referenced(crafting,tree.prop(reward,'myLootTable'),'loot/loottables','.mloottable')
            targets=direct_drops(table,items,{})
            if targets:
                rows[uid(reward)]=dict(kind='mission_item',entry=entry,entry_uid=identity,source=source,reward_uid=uid(reward),
                    table=table_file,table_uid=uid(table),targets=sorted(targets),verification='native_only',
                    display_text='「'+title+'」一次性任务奖励')
    crafting.unit(['routes','mission_item'],rows)


def dark_zone_drops(crafting,items):
    source='rogue/game system data/juice/ai/npc/npc_hostile_base.mnpc'
    npc=reference_nodes(crafting,source,'6B33C8FE5508485C0C16C0102244620F')
    root_file,root=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
    roles=(('elite','32D246155ADF5E5700007298F1149776','精英'),('named','32D246155ADF5E7F0000729B57BB45F8','具名'))
    grants={}
    for role,table_uid,label in roles:
        context=dict(dark_zone=True,zone_type='Default',elite=role=='elite',named=role=='named',floor=0)
        for _,link in drop_branches(root,'LootTableItem',context):
            raw=tree.prop(link,'myTable')
            if tree.reference(raw)['uid']!=table_uid:continue
            table_file,table=referenced(crafting,raw,'loot/loottables','.mloottable')
            for target in direct_drops(table,items,context):
                grants.setdefault(target,{})[label]={'table':table_file,'table_uid':table_uid,'context':context}
    rows={}
    for target,entries in grants.items():
        labels='或'.join(entries)
        row=rows.setdefault(labels,dict(kind='dark_zone_npc',entry=source,entry_uid=uid(npc),source=root_file,
            table_uid=uid(root),runtime_witnesses=list(entries.values()),targets=[],verification='native_only',
            display_text='暗区'+labels+'敌人掉落'))
        row['targets'].append(target)
    for row in rows.values():row['targets'].sort()
    crafting.unit(['routes','dark_zone_npc'],rows)


def bundle_catalog(crafting):
    caches={}
    for namespace in ('hunter','rogue'):
        folder=crafting.native.file(namespace+'/game system data/juice/item')
        for path in sorted(folder.glob('*.mitem')):
            if b'\nBundleItem ' not in path.read_bytes():continue
            source=path.relative_to(crafting.native.root).as_posix()
            for cache in crafting.document(source)['children']:
                if not cache['header'].startswith('BundleItem '):continue
                try:
                    identity=uid(cache)
                    native=crafting.native.record(source,identity)
                    caches[identity]={'source':source,'tags':item_tags(crafting.native,native),
                        'obtainable':scalar(crafting.native,native,'myIsObtainable','TRUE')=='TRUE',
                        'key_required':bool(crafting.native.member(native,'myCurrencyRequirement'))}
                except (KeyError,ValueError,OSError) as error:crafting.missing(source,error)
    return caches


def equipment_vendors(crafting,items,supports_prototype):
    rows={}
    caches=bundle_catalog(crafting)
    supplies={key:[] for key in caches}
    dc='hunter/baked_maps/672729d158ff58240000831f17e6ca15/'
    for name,identity,host,label in (
        ('hun_vendor_equipment_boo','BFADE5F95BC058E60002ED41E62E1650',JUICE+'ai/npc/vendor_boo_indoor.mnpc','白宫装备商人'),
        ('hun_vendor_equipment_haven','83ED36DA5DCD6375000355D8CD1C6647',JUICE+'ai/npc/civ_hav_settlement_vendor_publicspace_marcosiracusa.mnpc','避风港装备商人'),
        ('hun_vendor_conflict_publicspace','373FA64D6A9AEF28000BD9DC3959515F',dc+'ts[0,0,-40]_b[0].mbucket.decompiled',''),
        ('hun_vendor_specops','B3CF2E92617FE924000363EA0094594E',dc+'ts[0,0,-80]_b[0].mbucket.decompiled','倒计时商人'),
        ('hun_vendor_entrance_sd_dungeons','A719E91463C674CF0023BAF0955CD965',dc+'ts[120,0,-40]_b[0].mbucket.decompiled','下降模式 NSA 商店')):
        source=JUICE+'vendors/vendor configs/'+name+'.mvendorconfig'
        vendor=reference_nodes(crafting,source,identity)
        if host.endswith('.mnpc'):
            bound=any(tree.prop(n,'myVendorConfig','').strip('"')==source for n in tree.walk(crafting.document(host)))
        else:
            bound=f'vendorConfig = #{identity},' in crafting.native.file(host).read_text('utf-8-sig')
        if not bound:raise ValueError('Missing vendor placement: '+source)
        schedule=tree.prop(vendor,'myGameScheduleForRestock')
        overrides=tree.child(vendor,'myLootTableList')
        if overrides and (overrides['properties'] or overrides['children']) or schedule not in ('WeeklyResetSchedule','DailyResetSchedule'):
            raise ValueError('Unresolved vendor schedule or stock overrides: '+source)
        table_file,table=referenced(crafting,tree.prop(vendor,'myLootTable'),'loot/loottables','.mloottable')
        context={'level':40,'progression_tier':'WarlockLevel40'}
        ordinary=direct_drops(table,items,context)
        all_qualities=direct_drops(table,items,context,supports_prototype=supports_prototype)
        label=label or crafting.text(tree.prop(vendor,'myUIName'))
        for cache_uid in sorted(direct_drops(table,caches,context)):
            if not caches[cache_uid]['key_required']:
                supplies[cache_uid].append(dict(vendor=source,vendor_uid=identity,restock=schedule,placement=host,
                    table=table_file,table_uid=uid(table),context=context))
        for suffix,targets in [('',ordinary),('（原型）',all_qualities-ordinary)]:
            if not targets:continue
            rows[identity+(':prototype' if suffix else '')]=dict(kind='equipment_vendor',entry=source,entry_uid=identity,source=table_file,
                table_uid=uid(table),placement=host,restock=schedule,targets=sorted(targets),runtime_witnesses=[context],
                verification='native_only',display_text=label+'轮换出售'+suffix)
    crafting.unit(['routes','equipment_vendor'],rows)
    from .native_cache_rewards import progression_supply, regular_cache_contents
    progression_supply(crafting,caches,supplies)
    special={r['entry_uid'] for unit in crafting.units if unit['path'][:1]==['routes'] and unit['path'][1]
             in ('named_cache','exotic_cache','reconstructed_cache','season_weapon_cache') for r in unit['value'].values()}
    # These identities already have specialized rules, including conditional exotic rewards.
    # Both the generic season reward and the rotating textile slot select the
    # current season's box. The Countdown vendor mirrors that specific identity.
    season_file=LOOT+'ltref_sealed_cache_season_cache.mloottable'
    season=reference_nodes(crafting,season_file,'83ED36DA5DDBEE2D0003597657461589')
    textile=LOOT+'ltref_vendor_textiles_week1.mloottable'
    textile_table,=[n for n in crafting.document(textile)['children'] if n['header'].startswith('LootTable ')]
    season_slots=direct_drops(season,caches,{'level':40}) & direct_drops(textile_table,caches,{'level':40})
    for target in sorted(season_slots):
        for supply in supplies[target]:
            if 'vendor' in supply:supply.update(availability='season_slot',season_pool=season_file,textile_pool=textile)
    regular_cache_contents(crafting,items,caches,supplies,special)
    crafting.unit(['source_contexts','cache_supply'],supplies)
    from .native_blueprint_rewards import cache_windows
    crafting.unit(['source_contexts','cache_windows'],cache_windows(crafting,caches))


def world_activities(crafting,collect,items):
    mission_file='rogue/game system data/juice/mission/rooftops_introduction_parttwo.mmission'
    mission,=[n for n in crafting.document(mission_file)['children'] if tree.prop(n,'myReward')]
    unlock_file,unlock=referenced(crafting,tree.prop(mission,'myReward'),'rewards','.mreward')
    flags={tree.reference(tree.prop(n,'myPersistentFlag'))['uid'] for n in tree.walk(unlock)
           if n['header'].startswith('RewardPersistentFlag ') and tree.prop(n,'myIsRewardUsedAsTeaser','FALSE')=='FALSE'}
    rows={}
    for filename,activity_type,label in [('propaganda_activity','PropagandaBroadcast','宣传广播'),('street_execution','StreetExecution','公开处决')]:
        entry=JUICE+'livingworldsimulation/activities/'+filename+'.mlivingworldsimulationactivity'
        activity,=[n for n in crafting.document(entry)['children'] if n['header'].startswith('LivingWorldSimulationActivity ')]
        flag=tree.reference(tree.prop(activity,'myRequiredPersistentFlag'))['uid']
        if flag not in flags or tree.prop(activity,'myLivingWorldSimulationActivityType')!=activity_type:continue
        # The ordinary Outcast encounter is enabled by settlement progress. Its formula allows
        # a thriving hostile site at defence level 2 in DC. Unknown event gates stay unresolved.
        start=tree.child(activity,'myStartConditions')
        if not start or start['properties']:continue
        allowed=True
        for gate in start['children']:
            base=tree.prop(gate,'myFormula')
            if base not in ('CodeRef_IsThriving','1'):allowed=False
            for branch in tree.walk(gate):
                condition=tree.prop(branch,'myCondition')
                if condition and not (condition=='"Site.DefenceLevel > 1"' and tree.prop(branch,'myFormula')=='1'
                        or condition.startswith('"Site.Faction = Faction.Cleaners AND (Site.NamedZones.') and tree.prop(branch,'myFormula')=='0'):
                    allowed=False
        if not allowed:continue
        group_file,group=referenced(crafting,tree.prop(activity,'myCultistsReward'),'rewards','.mreward')
        if reward_difficulties(group)!=set(DIFFICULTIES):continue
        for ref,_ in tree.child(group,'myRewardReferences')['properties']:
            if not ref.startswith('RewardLoot '):continue
            leaf_file,leaf=referenced(crafting,ref[ref.index('<'):],'rewards','.mreward')
            # rewards.fruit limits myRewardOnce to mission payouts.
            activity_leaf={**leaf,'properties':[v for v in leaf['properties'] if v[0]!='myRewardOnce TRUE']}
            if reward_difficulties(activity_leaf)!=set(DIFFICULTIES):continue
            table_file,table=referenced(crafting,tree.prop(leaf,'myLootTable'),'loot/loottables','.mloottable')
            for pool in tree.child(table,'myLootGroups')['children']:
                if tree.prop(pool,'myLootItemList')!='= ItemList_Equipment_Gear '+'0'*32:continue
                from .native_sources import groups_allow_drop,conditions
                if not groups_allow_drop([pool]) or conditions(pool) or ' : ' in pool['header']:continue
                listing='hunter/game system data/rejuice/itemlist_equipment_gear.rejuice'
                matches=collect('world_activity',listing,entry,uid(activity),'LootItemList ItemList_Equipment_Gear',objects=items,strict=True)
                for key,row in matches.items():
                    context={'dark_zone':False,'faction':'Cultists','cp_level':2,'level':40}
                    try:enabled=all(permits(c,context) for c in row['conditions'])
                    except (KeyError,ValueError):enabled=False
                    if enabled:
                        row.update(display_text=label,entry_scope='route',runtime_witnesses=[dict(context,unlock=unlock_file,
                            mission=mission_file,flag_uid=flag,group=group_file,reward=leaf_file,table=table_file)],pool_uid=uid(table))
                        rows[key]=row
    crafting.unit(['routes','world_activity'],rows)


def project(crafting,collect,items,records,blueprints):
    @lru_cache(maxsize=None)
    def supports_prototype(target):
        item=crafting.native.member(records[target],'myValidQualities')
        return item and any(p.get('value_type')=='ItemQuality' and p['raw_value']=='Prototype'
                            and len(p['context'])==2 and p['context'][1]['resource_type']=='myValidQualities'
                            for p in item['properties'])
    for kind,fn in [('season_weapon_cache',lambda:season_caches(crafting,items,supports_prototype)),
                    ('dark_zone_npc',lambda:dark_zone_drops(crafting,items)),
                    ('equipment_vendor',lambda:equipment_vendors(crafting,items,supports_prototype)),
                    ('raid_cache',lambda:raid_caches(crafting,items,blueprints)),('boss_drop',lambda:boss_drops(crafting,items)),
                    ('mission_item',lambda:mission_items(crafting,items)),('world_activity',lambda:world_activities(crafting,collect,items))]:
        try:fn()
        except (OSError,ValueError,KeyError,StopIteration) as error:crafting.missing(kind,error)
    try:
        rows={};context={}
        for name,identity in GUARDIANS.items():
            entry=JUICE+'ai/npc/rog_boss_'+name+'_dru_rogueagent.mnpc'
            npc=reference_nodes(crafting,entry,identity)
            if tree.prop(npc,'myArchetype')!='Guardian':raise ValueError('NPC archetype changed')
            source,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
            selected=collect('guardian_drop',source,entry,identity,scope=table['header'],strict=True)
            runtime(selected,DIFFICULTIES[1:])
            for row in selected.values():row['context_refs']=[entry,source]
            rows.update(selected);context.update({entry:entry_context(npc),source:tree.semantic(table)})
        crafting.unit(['source_contexts','guardian_drop'],context)
        crafting.unit(['routes','guardian_drop'],rows)
    except (OSError,ValueError,KeyError,TypeError) as error:crafting.missing('guardian_drop',error)
    for kind,filename,identity,leaf,climax in (
        ('pearl_reward','mm53_thepearl','A719E9146903596F0007F1299C677566','373FA64D6AD77B060037FE94E12DE187',None),
        ('airport_climax_reward','jnv04_airport','0B9940F36A2015BD00080226FCA2E036','373FA64D6ABF8774001C3144FFF0DF6A',
         (JUICE+'mission/prime target climax data/ptclimax_y8s3_jnv04_airport.mmissionprimetargetclimaxdata','0B9940F36A2016760008024D6A0F5909',
          JUICE+'primetargetcampaign/y8s3_prime_target_ptplaylist.mprimetargetcampaignplaylist','0B9940F36A201BEA000401073BCDED53'))):
        try:crafting.unit(['routes',kind],mission(crafting,collect,kind,filename,identity,leaf,climax))
        except (OSError,ValueError,KeyError,TypeError) as error:crafting.missing(kind,error)
