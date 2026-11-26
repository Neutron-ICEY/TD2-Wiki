"""Registered recipe grants from season tracks, projects and crafting unlocks."""
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from . import native_tree as tree
from .native_source_rules import uid
from .native_sources import ancestor_path, reference_nodes
from .native_special_sources import JUICE, list_reference, referenced

SCHEDULE=JUICE+'scheduling/season_wrapper_schedule.mgameschedule'
PROJECTS=JUICE+'projects/projects.juice'


def blueprint_index(blueprints):
    files={}
    for target,bp in blueprints.items():
        if bp['targets']:files.setdefault(bp['source'].lower(),[]).append(target)
    return files


def blueprint_target(crafting,files,reward):
    if tree.prop(reward,'myIsRewardUsedAsTeaser','FALSE')!='FALSE':return []
    source=tree.prop(reward,'myItemTypeFile','').strip('"').lower()
    ids=files.get(source,[])
    if len(ids)>1:raise ValueError('Ambiguous blueprint reward: '+source)
    if ids:reference_nodes(crafting,source,ids[0])
    return ids


def retaliation(crafting,blueprints):
    from .native_drop_sources import direct_drops
    from .native_special_sources import reward_difficulties, DIFFICULTIES
    source=JUICE+'retaliation/retaliationsettings.juice'
    faction_file=JUICE+'faction/factions.juice'
    settings,=[n for n in crafting.document(source)['children'] if tree.child(n,'myFactionRetaliation')]
    rows={}
    unresolved=[]
    for entry in tree.child(settings,'myFactionRetaliation')['children']:
        if not entry['header'].startswith('FactionRetaliationData '):continue
        zones=[list_reference(p)['uid'] for n in tree.walk(tree.child(entry,'myMapNamedZones'))
               for p,_ in n['properties'] if p.startswith('NamedZone ')]
        if not zones:continue
        faction_uid=tree.reference(tree.prop(entry,'myFaction'))['uid']
        faction=reference_nodes(crafting,faction_file,faction_uid)
        for field,action in [('myCompletionReward','defend_territory'),('myKillTeamDefeatedReward','kill_squad')]:
            raw=tree.prop(entry,field)
            if not raw or raw.endswith('NULLREFERENCE'):continue
            group_file,group=referenced(crafting,raw,'rewards','.mreward')
            if reward_difficulties(group)!=set(DIFFICULTIES):continue
            for leaf in (tree.child(group,'myRewards') or {}).get('children',[]):
                if not leaf['header'].startswith('RewardLoot ') or reward_difficulties(leaf)!=set(DIFFICULTIES):continue
                ref=tree.prop(leaf,'myLootTable')
                try:
                    table_file,table=referenced(crafting,ref,'loot/loottables','.mloottable')
                except (ValueError,OSError) as error:
                    unresolved.append(dict(faction_uid=faction_uid,action=action,group=group_file,
                        leaf_uid=uid(leaf),table=list_reference(ref),reason=str(error)))
                    continue
                for difficulty in ('Normal','Hard','Challenge','Heroic'):
                    context={'global_difficulty':difficulty}
                    for target in direct_drops(table,blueprints,context):
                        key=':'.join([faction_uid,field,uid(leaf),target])
                        row=rows.setdefault(key,dict(kind='retaliation_blueprint',entry=source,entry_uid=uid(leaf),source=table_file,
                            table_uid=uid(table),group=group_file,faction=crafting.text(tree.prop(faction,'myUIName')),
                            faction_uid=faction_uid,zones=zones,action=action,targets=[target],runtime_witnesses=[],verification='native_only'))
                        row['runtime_witnesses'].append(context)
    crafting.unit(['routes','retaliation_blueprint'],rows)
    crafting.unit(['source_contexts','retaliation_blueprint'],{'unresolved':unresolved})


def legacy_manhunts(crafting):
    source='hunter/game system data/rejuice/progression_rewards_data.rejuice'
    unlocks={}
    for level in tree.walk(crafting.document(source)):
        if not level['header'].startswith('IntervallicRewardRule ') or any(
                tree.prop(level,k)!='40' for k in ('myMinLevelRange','myMaxLevelRange')):continue
        reward=tree.prop(level,'myRewardAsset')
        if not reward or reward.endswith('NULLREFERENCE'):continue
        group_file,group=referenced(crafting,reward,'rewards','.mreward')
        references=tree.child(group,'myRewardReferences')
        for raw,_ in (references or {}).get('properties',[]):
            if not raw.startswith('RewardGroup '):continue
            ref_file,ref=referenced(crafting,raw,'rewards','.mreward')
            for node in (tree.child(ref,'myRewards') or {}).get('children',[]):
                if not node['header'].startswith('RewardPrimeTargetClimaxMissionPermanentUnlock '):continue
                if tree.prop(node,'myIsRewardUsedAsTeaser','FALSE')!='FALSE':continue
                climax=tree.prop(node,'myPermanentlyUnlockedPrimeTargetClimaxMission','').strip('"')
                if not climax:continue
                target,=[c for c in crafting.document(climax)['children'] if c['header'].startswith('MissionPrimeTargetClimaxData ')]
                unlocks[uid(target)]=dict(level=40,progression=source,reward=group_file,group=ref_file,unlock_uid=uid(node),climax=climax)
    crafting.unit(['source_contexts','legacy_manhunts'],unlocks)


def mission_boss_blueprints(crafting,blueprints):
    from .native_drop_sources import direct_drops
    origin='rogue/game system data/juice/mission/mm10_nasahq.mmission'
    mission=reference_nodes(crafting,origin,'A0FB99F459799AE6000036472C477173')
    entry=JUICE+'ai/npc/mil_boss_nasa_tank.mnpc'
    npc=reference_nodes(crafting,entry,'6B33C8FE5AAD241A00025942CA26760B')
    placement='hunter/baked_maps/672729d158ff58240000831f17e6ca15/ts[1680,0,-1440]_b[0].mbucket.decompiled'
    bound=any(tree.prop(n,'myNPCConfig','').strip('"')==entry for n in tree.walk(tree.child(mission,'myBossPreviewData')))
    rows={}
    if bound and 'UID = #&'+uid(npc)+',' in crafting.native.file(placement).read_text('utf-8-sig'):
        table_file,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
        currency_file=JUICE+'currencies/currencies.rejuice'
        part=reference_nodes(crafting,currency_file,'4CDCE5B25BE6D01D00033057FAABEB96')
        limits=tree.child(part,'myStackingLimits')
        if tree.prop(limits,'myHasUpperCap')=='TRUE' and tree.prop(limits,'myUpperCap')=='1':
            for target,bp in blueprints.items():
                if 'Desert_Eagle_Exotic' not in bp['tags'] or bp['purpose']!='craft':continue
                name=PurePosixPath(bp['source']).stem
                context={'inventory':{name:False},'currency_percent':{uid(part):100}}
                obj={target:bp}
                if target not in direct_drops(table,obj,context):continue
                if direct_drops(table,obj,{**context,'currency_percent':{uid(part):0}}) or direct_drops(table,obj,{**context,'inventory':{name:True}}):continue
                label='持有「'+crafting.text(tree.prop(part,'myUIName'))+'」后，击败'+crafting.text(tree.prop(npc,'myUIName'))
                rows[target]=grant('mission_boss_blueprint',entry,uid(npc),target,label,origin=origin,placement=placement,
                    source=table_file,table_uid=uid(table),currency=currency_file,currency_uid=uid(part),runtime_witnesses=[context])
    rows.update(invaded_boss_blueprint(crafting,blueprints))
    crafting.unit(['routes','mission_boss_blueprint'],rows)


def capped_parts(crafting,identities):
    parts={}
    for identity in identities:
        obj=reference_nodes(crafting,JUICE+'currencies/currencies.rejuice',identity)
        cap=tree.child(obj,'myStackingLimits')
        if tree.prop(cap,'myHasUpperCap')!='TRUE' or tree.prop(cap,'myUpperCap')!='1':
            raise ValueError('Quest component cap changed: '+identity)
        parts[identity]=crafting.text(tree.prop(obj,'myUIName'))
    return parts


def invaded_boss_blueprint(crafting,blueprints):
    from .native_drop_sources import direct_drops
    origin='rogue/game system data/juice/mission/mm01_grandhyatt.mmission'
    mission=reference_nodes(crafting,origin,'A0FB99F459799A1C000035FF63729AE8')
    entry=JUICE+'ai/npc/end_boss_grandhyatt_sniper.mnpc'
    npc=reference_nodes(crafting,entry,'6B33C8FE5A8A9B0600053D61E0B76626')
    placement='hunter/baked_maps/672729d158ff58240000831f17e6ca15/ts[760,0,120]_b[0].mbucket.decompiled'
    if not any(tree.prop(n,'myNPCConfig','').strip('"')==entry for n in tree.walk(tree.child(mission,'myInvadedBossPreviewData'))):return {}
    if 'UID = #&'+uid(npc)+',' not in crafting.native.file(placement).read_text('utf-8-sig'):return {}
    schedule=JUICE+'scheduling/endgame_invasion_schedule.mgameschedule'
    entrypoint=reference_nodes(crafting,schedule,'C3475E355B45E95700054AEE38CA4431')
    pool_settings=tree.child(entrypoint,'myPoolSettings')
    if not any(n['header'].startswith('GameScheduleCadenceWeekly ') for n in tree.child(pool_settings,'myPoolCadence')['children']):return {}
    pool_file,pool=referenced(crafting,tree.prop(pool_settings,'myPool'),'scheduling','.mgameschedulepool')
    invasion_uid='C3475E355B0423AA000092866236DBB7'
    links=[tree.prop(n,'myInvasion') for n in tree.walk(pool) if tree.prop(n,'myInvasion','').endswith(' '+invasion_uid)]
    if len(links)!=1:return {}
    invasion_file,invasion=referenced(crafting,links[0],'invasion','.minvasion')
    if not any(tree.prop(n,'myMission','').endswith(' '+uid(mission)) for n in tree.walk(invasion)):return {}
    table_file,table=referenced(crafting,tree.prop(npc,'myLootTable'),'loot/loottables','.mloottable')
    scope='4CDCE5B25BE70E5E00033068447B0608'
    others=['4CDCE5B25BE70E5E0003306962294ED9','4CDCE5B25BE70E5E0003306AE1AF4EED','4CDCE5B25BE70E5E0003306B41E022F6']
    parts=capped_parts(crafting,[scope,*others])
    tier_file='hunter/game system data/fruit/world/progressiontier.fruit'
    enum,=[n for n in crafting.document(tier_file)['children'] if n['header']=='enum ProgressionTier']
    tiers=[p for p,_ in enum['properties']]
    rows={}
    for target,bp in blueprints.items():
        if bp['purpose']!='craft' or 'AWM_Exotic' not in bp['tags']:continue
        item,=bp['targets']
        name='player_weapon_marksmanrifle_awm_exotic_v1'
        files=[p for p in crafting.native.includes(bp['source']) if PurePosixPath(p).stem==name]
        if len(files)!=1:continue
        owned=reference_nodes(crafting,files[0],item)
        base={'world_tier':'WarlockLevel40','world_tiers':tiers,'inventory':{name:False}}
        def awards(currencies,**override):
            return target in direct_drops(table,{target:bp},{**base,'currency_percent':currencies,**override})
        def inventory(*held):return {p:100 if p in held else 0 for p in parts}
        if not all(awards(inventory(scope,p)) for p in others) or awards(inventory(scope)) or awards(inventory(*others)):continue
        if awards(inventory(*parts),inventory={name:True}) or awards(inventory(*parts),world_tier='WorldTier4'):continue
        label='入侵'+crafting.text(tree.prop(mission,'myHeadingText'))+'：世界等级 5 起，持有「'+parts[scope]+'」及复仇女神的枪托、枪机或枪管之一，尚未持有成品时击败'+crafting.text(tree.prop(npc,'myUIName'))
        rows[target]=grant('mission_boss_blueprint',entry,uid(npc),target,label,origin=origin,placement=placement,
            source=table_file,table_uid=uid(table),parts=parts,product_uid=uid(owned),schedule=schedule,pool=pool_file,
            invasion=invasion_file,tier_definition=tier_file,runtime_witnesses=[dict(level=40,world_tier='WarlockLevel40')])
    return rows


def mission_cache_blueprints(crafting,blueprints):
    from .native_drop_sources import direct_drops
    origin='rogue/game system data/juice/mission/mm04_worldbank.mmission'
    mission=reference_nodes(crafting,origin,'A0FB99F459799A7E00003617D563A5B9')
    entry='hunter/interaction/settings/interact_loot_table_faction_bla.minteractionsetup'
    crate=reference_nodes(crafting,entry,'075801E25B7E9ED90002A5D23F55894F')
    interaction='hunter/interaction/sets/interact_loot_table_faction_bla_set.propinteraction'
    dc='hunter/baked_maps/672729d158ff58240000831f17e6ca15/'
    placement=dc+'t[-520,0,120]_b[0]_[fe0764c55b0e7172001bbd900f453fc9].mbucket.decompiled'
    area=dc+'t[-520,0,120]_b[4].mbucket.decompiled'
    if 'interactionSetup = "'+interaction+'"' not in crafting.native.file(placement).read_text('utf-8-sig') or 'vol_mm04_WorldBank_Tracking' not in crafting.native.file(area).read_text('utf-8-sig'):return {}
    if not any(tree.prop(n,'myInteractionSettings','').endswith(' '+uid(crate)) for n in tree.walk(crafting.document(interaction))):return {}
    blocks={n['header'].split()[0]:n for n in crate['children']}
    if tree.prop(blocks['mySetup'],'myPropInteractionType')!='LootCrate':return {}
    req=blocks['myRequirements'];cost,=tree.child(req,'myResourcesRequired')['children']
    if any(n['header'] not in ('myResourcesRequired','myCharacterRequirements') for n in req['children']):return {}
    key=reference_nodes(crafting,JUICE+'currencies/currencies.rejuice',tree.reference(tree.prop(cost,'myCurrency'))['uid'])
    if tree.prop(cost,'myAmount')!='1' or tree.prop(tree.child(req,'myCharacterRequirements'),'myImmersionCharacterRequirement')!='NonImmersion':return {}
    table_file,table=referenced(crafting,tree.prop(blocks['myRewardSettings'],'myLootTable'),'loot/loottables','.mloottable')
    parts=capped_parts(crafting,['4CDCE5B25BE6F66A0003305CD78FB066','4CDCE5B25BE6F66A0003305D1668F046','4CDCE5B25BE6F66A0003305EBB50ED24'])
    context={'mission_uid':uid(mission),'currency_percent':dict.fromkeys(parts,100)}
    rows={}
    for target in direct_drops(table,blueprints,context):
        bp=blueprints[target]
        if bp['purpose']!='craft' or 'P90_Exotic' not in bp['tags']:continue
        if any(direct_drops(table,{target:bp},{**context,'currency_percent':{**context['currency_percent'],part:0}}) for part in parts):continue
        if direct_drops(table,{target:bp},{**context,'mission_uid':None}):continue
        label='集齐三个话匣子零件后，在'+crafting.text(tree.prop(mission,'myHeadingText'))+'用'+crafting.text(tree.prop(key,'myUIName'))+'开启势力箱'
        rows[target]=grant('mission_cache_blueprint',entry,uid(crate),target,label,origin=origin,placement=placement,area=area,
            interaction=interaction,source=table_file,table_uid=uid(table),key_uid=uid(key),parts=parts,runtime_witnesses=[context])
    return rows


def grant(kind,entry,entry_uid,target,text,**edges):
    return dict(kind=kind,entry=entry,entry_uid=entry_uid,targets=[target],
                display_text=text,verification='native_only',**edges)


def direct_recipes(crafting,group,files):
    if ' : ' in group['header'] or any(p.split(' ',1)[0] not in ('myRewardOnce','myIncludedInPreview') for p,_ in group['properties']):return
    if any(c['header'] not in ('myRewards','myRewardReferences') for c in group['children']):return
    for item in (tree.child(group,'myRewards') or {}).get('children',[]):
        if not item['header'].startswith('RewardItem ') or item['children']:continue
        if any(p.split(' ',1)[0] not in ('myItemTypeFile','myIsRewardUsedAsTeaser','myIncludedInPreview') for p,_ in item['properties']):continue
        for target in blueprint_target(crafting,files,item):yield target,uid(item)


def relative(source,path):
    return str(PurePosixPath(source).parent/path) if path.startswith('./') else path


def included_nodes(crafting,source,suffix,kind):
    for raw,_ in crafting.document(source)['properties']:
        if not raw.startswith('include '):continue
        path=relative(source,raw[8:].strip('"'))
        if path.endswith(suffix):
            for node in crafting.document(path)['children']:
                if node['header'].startswith(kind+' '):yield uid(node),(path,node)


def cache_windows(crafting,caches):
    from .native_drop_sources import direct_drops
    common=JUICE+'rewards/tieredrewardsets/tieredrewardcommon_seasons.mtieredrewardset'
    grants={}
    for tier in crafting.document(common)['children']:
        if not tier['header'].startswith('TieredReward '):continue
        source=tree.prop(tier,'myReward','').strip('"')
        if not source.endswith('.mreward'):continue
        source=relative(common,source)
        for group in crafting.document(source)['children']:
            if not group['header'].startswith('RewardGroup '):continue
            for leaf in (tree.child(group,'myRewards') or {}).get('children',[]):
                if not leaf['header'].startswith('RewardLoot ') or tree.prop(leaf,'myIsRewardUsedAsTeaser','FALSE')!='FALSE':continue
                ref=tree.prop(leaf,'myLootTable')
                if not ref or ref.endswith('NULLREFERENCE'):continue
                table_file,table=referenced(crafting,ref,'loot/loottables','.mloottable')
                for target in direct_drops(table,caches,{'level':40}):
                    grants.setdefault(uid(tier),[]).append((target,source,table_file))
    result={}
    wrappers=dict(included_nodes(crafting,SCHEDULE,'.mseasonwrapper','SeasonWrapper'))
    for window in tree.walk(crafting.document(SCHEDULE)):
        period=tree.prop(window,'myActiveTime')
        if not period or not window['header'].startswith('GameScheduleManualEntry '):continue
        for entry in (tree.child(window,'myEntries') or {}).get('children',[]):
            wr=tree.prop(entry,'mySeasonWrapper')
            if not wr or wr.endswith('NULLREFERENCE'):continue
            source,wrapper=wrappers[tree.reference(wr)['uid']]
            sets=dict(included_nodes(crafting,source,'.mtieredrewardset','TieredRewardSet'))
            for field in ('myTieredRewardSet','myExtensionTieredRewardSet'):
                ref=tree.prop(wrapper,field)
                if not ref or ref.endswith('NULLREFERENCE'):continue
                file,rewards=sets[tree.reference(ref)['uid']]
                for node in tree.walk(rewards):
                    for p,_ in node['properties']:
                        if not p.startswith(('myNormalReward <','myPremiumReward <')) or p.endswith('NULLREFERENCE'):continue
                        tier=list_reference(p)['uid']
                        for target,reward,table in grants.get(tier,[]):
                            evidence=dict(schedule=SCHEDULE,window_uid=uid(window),period=period,wrapper=source,tiers=file,
                                          tier_uid=tier,reward=reward,table=table)
                            rows=result.setdefault(target,[])
                            if evidence not in rows:rows.append(evidence)
    return result

def normal_track(crafting,wrapper_file,wrapper,candidates):
    raw=tree.prop(wrapper,'myTieredRewardSet')
    if not raw or raw.endswith('NULLREFERENCE'):return
    sets=dict(included_nodes(crafting,wrapper_file,'.mtieredrewardset','TieredRewardSet'))
    tiers,reward_set=sets[tree.reference(raw)['uid']]
    grants={uid(tier):relative(tiers,tree.prop(tier,'myReward','').strip('"'))
            for tier in crafting.document(tiers)['children'] if tier['header'].startswith('TieredReward ')}
    for rank in (tree.child(reward_set,'myNormalTierRewards') or {}).get('children',[]):
        raw=tree.prop(rank,'myNormalReward')
        if not raw or raw.endswith('NULLREFERENCE'):continue
        group_file=grants.get(tree.reference(raw)['uid'])
        if group_file not in candidates:continue
        groups=[n for n in crafting.document(group_file)['children'] if n['header'].startswith('RewardGroup ')]
        level=int(tree.prop(rank,'myScore'))
        if len(groups)==1 and level>0:yield tiers,reward_set,rank,level,group_file,groups[0]


def season_blueprints(crafting,blueprints,direct_rewards):
    files=blueprint_index(blueprints)
    candidates={r['source'] for r in direct_rewards.values() if any(t in blueprints for t in r['targets'])}
    wrappers=dict(included_nodes(crafting,SCHEDULE,'.mseasonwrapper','SeasonWrapper'))
    rows={}
    for window in tree.walk(crafting.document(SCHEDULE)):
        active=tree.prop(window,'myActiveTime')
        if not window['header'].startswith('GameScheduleManualEntry ') or not active:continue
        for event in (tree.child(window,'myEntries') or {}).get('children',[]):
            raw=tree.prop(event,'mySeasonWrapper','')
            if not event['header'].startswith('GameScheduleEntrySeasonWrapper ') or not raw or raw.endswith('NULLREFERENCE'):continue
            source,wrapper=wrappers[tree.reference(raw)['uid']]
            for tiers,track,rank,level,reward,group in normal_track(crafting,source,wrapper,candidates):
                for target,item_uid in direct_recipes(crafting,group,files):
                    rows[uid(event)+':'+uid(rank)+':'+target]=grant('season_blueprint',source,uid(rank),target,'',
                        schedule=SCHEDULE,schedule_uid=uid(event),active_time=active,tiers=tiers,
                        tiers_uid=uid(track),level=level,source=reward,reward_uid=item_uid)
    crafting.unit(['routes','season_blueprint'],rows)


def progression_blueprints(crafting,files):
    rows={}
    def record(group,source,entry,entry_uid,text,**edges):
        for target,item_uid in direct_recipes(crafting,group,files):
            rows[entry_uid+':'+item_uid]=grant('progression_blueprint',entry,entry_uid,target,text,
                source=source,reward_uid=item_uid,group_uid=uid(group),**edges)

    roster=JUICE+'base of operations/boosettings.juice'
    staff_uid='5D3E35F45B46126700045B46C264C3D5'
    settings,=[n for n in crafting.document(roster)['children'] if n['header'].startswith('BOOSettings ')]
    if any(list_reference(p)['uid']==staff_uid for p,_ in tree.child(settings,'myStaffRoster')['properties']):
        staff=JUICE+'base of operations/boo_staff_inaya_al-khaliq.mboostaff'
        npc=reference_nodes(crafting,staff,staff_uid)
        source,group=referenced(crafting,tree.prop(npc,'myReward'),'rewards','.mreward')
        record(group,source,staff,staff_uid,'招募'+crafting.text(tree.prop(npc,'myName'))+'解锁制作台',roster=roster)

    mission=JUICE+'mission/inc02_mission.mmission'
    raid=reference_nodes(crafting,mission,'2736B3655C6BF37800085D5EA715CCD7')
    source,group=referenced(crafting,tree.prop(raid,'myReward'),'rewards','.mreward')
    intel=JUICE+'item/rwitem_proj_crafting_gearset_cqc.mitem'
    item=reference_nodes(crafting,intel,'4CDCE5B25BEAE317000332671F523F09')
    intel_reward=tree.prop(item,'myReward').strip('"')
    intel_group,=[n for n in crafting.document(intel_reward)['children'] if n['header'].startswith('RewardGroup ')]
    pending=[(group,mission,[source]),(intel_group,intel,[intel_reward])]
    from .native_drop_sources import direct_drops
    from .native_sources import VENDOR
    vendor,=[n for n in crafting.document(VENDOR)['children'] if n['header'].startswith('VendorConfig ')]
    stock_file,stock=referenced(crafting,tree.prop(vendor,'myLootTable'),'loot/loottables','.mloottable')
    holster=JUICE+'item/rwitem_proj_crafting_exotic_cqe_01.mitem'
    intel=reference_nodes(crafting,holster,'4CDCE5B25CE4160400033A9085D057B3')
    if direct_drops(stock,{uid(intel):{'tags':tree.tags(intel,'myTags'),'obtainable':True}},{'level':40}):
        start=tree.prop(intel,'myReward').strip('"')
        first,=[n for n in crafting.document(start)['children'] if n['header'].startswith('RewardGroup ')]
        pending.append((first,holster,[VENDOR,stock_file,start]))
    issued_flags={}
    loot_rewards=[]
    while pending:
        group,entry,chain=pending.pop()
        if entry==mission:
            for leaf in (tree.child(group,'myRewards') or {}).get('children',[]):
                if tree.prop(leaf,'myIsRewardUsedAsTeaser','FALSE')!='FALSE' or leaf['children']:continue
                if leaf['header'].startswith('RewardPersistentFlag ') and tree.prop(leaf,'myPersistentFlagValue','TRUE')=='TRUE':
                    issued_flags[tree.reference(tree.prop(leaf,'myPersistentFlag'))['uid']]=chain
                if leaf['header'].startswith('RewardLoot ') and tree.prop(leaf,'myLootTable'):
                    loot_rewards.append((leaf,chain))
        for node in (tree.child(group,'myRewards') or {}).get('children',[]):
            if not node['header'].startswith('RewardProject '):continue
            if any(p.split(' ',1)[0] not in ('myProject','myProjectSource','myRewardOnce','myRewardHighlightType') for p,_ in node['properties']):continue
            difficulties=tree.child(node,'myValidMissionDifficulties')
            if any(c is not difficulties for c in node['children']):continue
            if difficulties and 'Normal' not in {p.rsplit(' ',1)[-1] for p,_ in difficulties['properties']}:continue
            project=reference_nodes(crafting,PROJECTS,tree.prop(node,'myProject'))
            reward,group_next=referenced(crafting,tree.prop(project,'myCompletionReward'),'rewards','.mreward')
            if reward in chain:raise ValueError('Cyclic crafting project '+reward)
            name=crafting.text(tree.prop(project,'myName'))
            label='在完成铁驹行动后，完成 ['+name+'] 计划' if entry==mission else '完成「'+name+'」计划'
            record(group_next,reward,entry,uid(project),label,projects=PROJECTS,project_chain=chain)
            pending.append((group_next,entry,chain+[reward]))
    # Two independently issued Iron Horse projects set the flags for the final project.
    final_file=JUICE+'item/rwi_proj_crafting_exotic_cqf_3.mitem'
    intel=reference_nodes(crafting,final_file,'075801E25E99A0FC00035A5E77D3218A')
    required={'075801E25E99C524000AF906D5889629','075801E25E99C524000AF9071C4DF974'}
    if required<=issued_flags.keys():
        flags={flag:True for flag in required}
        for leaf,chain in loot_rewards:
            pool_file,pool=referenced(crafting,tree.prop(leaf,'myLootTable'),'loot/loottables','.mloottable')
            item={uid(intel):{'tags':tree.tags(intel,'myTags'),'obtainable':True}}
            if not direct_drops(pool,item,{'flags':flags}):continue
            if any(direct_drops(pool,item,{'flags':{**flags,flag:False}}) for flag in flags):continue
            start=tree.prop(intel,'myReward').strip('"')
            grant_node,=[n for n in crafting.document(start)['children'] if n['header'].startswith('RewardProject ')]
            project=reference_nodes(crafting,PROJECTS,tree.prop(grant_node,'myProject'))
            reward,final=referenced(crafting,tree.prop(project,'myCompletionReward'),'rewards','.mreward')
            label='铁驹行动 - 完成两个组装计划后，完成「'+crafting.text(tree.prop(project,'myName'))+'」'
            record(final,reward,mission,uid(project),label,projects=PROJECTS,required_flags=issued_flags,
                   project_chain=chain+[pool_file,final_file,start,reward])
    rows.update(summit_project(crafting,files))
    crafting.unit(['routes','progression_blueprint'],rows)


def summit_project(crafting,files):
    from .native_drop_sources import direct_drops
    from .native_special_sources import reward_difficulties,DIFFICULTIES
    source=JUICE+'mission/skyscraperdata.juice'
    floor=reference_nodes(crafting,source,'6F2AF9195F44CFDE00035B89EBFCF0B1')
    if tree.prop(floor,'myMaxFloor')!='100' or tree.prop(floor,'myIsBossFloor')!='TRUE':return {}
    group_file,group=referenced(crafting,tree.prop(floor,'myReward'),'rewards','.mreward')
    if reward_difficulties(group)!=set(DIFFICULTIES):return {}
    leaf=reference_nodes(crafting,group_file,'96C6A7A35F71EEBF0003B661C354A5E3')
    if leaf not in tree.child(group,'myRewards')['children'] or reward_difficulties(leaf)!=set(DIFFICULTIES):return {}
    table_file,table=referenced(crafting,tree.prop(leaf,'myLootTable'),'loot/loottables','.mloottable')
    intel_file=JUICE+'item/rwi_proj_crafting_exotic_cqg.mitem'
    intel=reference_nodes(crafting,intel_file,'075801E25F4C90B80003652905F2F5BB')
    item={uid(intel):{'tags':tree.tags(intel,'myTags'),'obtainable':True}}
    start=tree.prop(intel,'myReward').strip('"')
    first,=[n for n in crafting.document(start)['children'] if n['header'].startswith('RewardProject ')]
    p1=reference_nodes(crafting,PROJECTS,tree.prop(first,'myProject'))
    second_file,second=referenced(crafting,tree.prop(p1,'myCompletionReward'),'rewards','.mreward')
    follow,=[n for n in tree.child(second,'myRewards')['children'] if n['header'].startswith('RewardProject ')]
    p2=reference_nodes(crafting,PROJECTS,tree.prop(follow,'myProject'))
    final_file,final=referenced(crafting,tree.prop(p2,'myCompletionReward'),'rewards','.mreward')
    parts=capped_parts(crafting,['075801E25F3FE66A0003650222061813','075801E25F3FE66A00036503064A14F4',
        '075801E25F3FE66A0003650477402C8C','075801E25F3FE66A0003650538F2E914','075801E25F3FE66A000365062A26A899'])
    rows={}
    for target,reward_uid in direct_recipes(crafting,final,files):
        ingredient=next(path for path,ids in files.items() if target in ids)
        context={'currency_percent':dict.fromkeys(parts,100),'active_projects':{uid(p1):False,uid(p2):False},
                 'inventory':{PurePosixPath(ingredient).stem:False}}
        if not direct_drops(table,item,context):continue
        if any(direct_drops(table,item,{**context,'currency_percent':{**context['currency_percent'],k:0}}) for k in parts):continue
        label='集齐五个零件后通关高峰大厦 100 层，完成「'+crafting.text(tree.prop(p2,'myName'))+'」计划'
        rows[target]=grant('progression_blueprint',source,uid(p2),target,label,source=final_file,reward_uid=reward_uid,
            project_chain=[group_file,table_file,intel_file,start,second_file,final_file],parts=parts,runtime_witnesses=[context])
    return rows


def project_window(crafting,schedule,event):
    parents=ancestor_path(schedule,event)
    season=next((n for n in parents if n['header'].startswith('GameScheduleManualEntry ')),None)
    if not season:return None
    active=tree.prop(season,'myActiveTime')
    if not active:return None
    offsets=[n for n in parents if n['header'].startswith('OffsetGameScheduleManualEntry ')]
    if not offsets:return active
    if len(offsets)!=1:return None
    offset=offsets[0]
    schedule_uid=tree.prop(offset,'myGameSchedule')
    if schedule_uid!='0AF8F42D66A1543200036DE3712ADF3D':return None
    project_schedule=reference_nodes(crafting,JUICE+'scheduling/seasonal_projects_schedule.mgameschedule',schedule_uid)
    if int(tree.prop(project_schedule,'myNumberOfEntriesToSelect','1'))<1:return None
    start,end=(datetime.fromisoformat(value) for value in active.strip('"').split(' to '))
    unit={'Weeks':'weeks','Days':'days','Hours':'hours'}[tree.prop(offset,'myTimeUnit','Weeks')]
    duration=int(tree.prop(offset,'myDuration','1'))
    delay=int(tree.prop(offset,'myOffset','0'))
    if duration==0 or duration < -1 or delay < 0:return None
    start+=timedelta(**{unit:delay})
    if duration!=-1:end=min(end,start+timedelta(**{unit:duration})-timedelta(seconds=1))
    return f'"{start} to {end}"' if start<=end else None


def journey_blueprints(crafting,files):
    source=JUICE+'projects/projectsseasonaljourney.juice'
    projects={uid(p):p for p in crafting.document(source)['children'] if p['header'].startswith('Project ')}
    rows={}
    schedule=crafting.document(SCHEDULE)
    for event in tree.walk(schedule):
        additional=tree.child(event,'myAdditionalProjects')
        if not additional or not event['header'].startswith('GameScheduleEntryProject '):continue
        active={list_reference(p)['uid'] for p,_ in additional['properties'] if p.startswith('Project ')}
        selected=sorted(active & projects.keys())
        if not selected:continue
        active_time=project_window(crafting,schedule,event)
        for identity in selected:
            for node in (tree.child(projects[identity],'myObjectives') or {}).get('children',[]):
                if not node['header'].startswith('ProjectObjectiveActivityCompleteProject '):continue
                raw=tree.prop(node,'myCompletionReward')
                prereqs=tree.child(node,'myProjects')
                if not raw or raw.endswith('NULLREFERENCE') or not prereqs:continue
                required={p.rsplit(' ',1)[-1] for p,_ in prereqs['properties']}
                if not required or not required<=active:continue
                reward,group=referenced(crafting,raw,'rewards','.mreward')
                for target,item_uid in direct_recipes(crafting,group,files):
                    rows[identity+':'+item_uid]=grant('journey_blueprint',source,identity,target,'',schedule=SCHEDULE,
                        schedule_uid=uid(event),required_projects=sorted(required),source=reward,reward_uid=item_uid,
                        active_time=active_time)
    crafting.unit(['routes','journey_blueprint'],rows)
