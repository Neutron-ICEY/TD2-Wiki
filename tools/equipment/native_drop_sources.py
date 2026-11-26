"""Resolve shared drop entries against concrete supported runtime contexts."""
from math import isfinite
from . import native_tree as tree
from .native_sources import conditions, ancestor_path, groups_allow_drop, matches, reference_nodes, LOOT


def name(node):
    return node['header'].split(' ', 1)[1].split(' : ')[0].split(' <')[0].strip('"')


def permits(node, context):
    if node is None:return True
    kind=node['type'];props={}
    for raw in node.get('properties',[]):
        key,value=raw.split(' ',1)
        if key in props:raise ValueError('Duplicate runtime condition property')
        props[key]=value
    negated=props.pop('myIsNegated','FALSE')
    if negated not in ('TRUE','FALSE'):raise ValueError('Unknown negation')
    children=node.get('children',[])
    if kind in ('myConditions','myConditionList','myConditionsA','myConditionsB','LootConditions','ORCondition'):
        values=[permits(child,context) for child in children]
        result=any(values) if kind=='ORCondition' else all(values)
        if kind=='ORCondition' and not values:raise ValueError('Empty OR condition')
    else:
        if children:raise ValueError('Unexpected runtime condition children')
        if kind=='LootConditionIsInDarkZone':
            result=context['dark_zone']
            evaluate=props.pop('myEvaluateType','FALSE')
            if evaluate=='TRUE':
                zone=props.pop('myDarkZoneType','Default')
                result=result and context['zone_type']==zone
            elif evaluate!='FALSE':raise ValueError('Invalid zone type flag')
        elif kind=='LootConditionHasItem':result=context['inventory'][props.pop('myRequiredItemType')]
        elif kind=='LootConditionPlayerCurrencyPercentage':
            currency=tree.reference(props.pop('myCurrencyDefinition'))['uid']
            op=props.pop('myOperator','LessThan')
            value=context['currency_percent'][currency];limit=float(props.pop('myCurrencyPercentage','100'))
            result={'GreaterThanOrEqual':value>=limit,'GreaterThan':value>limit,'LessThan':value<limit}[op]
        elif kind=='LootConditionIsProjectAvailable':
            project=tree.reference(props.pop('myProject'))['uid']
            if props.pop('myIsInProgress',None)!='TRUE' or props.pop('myIsCompletedButNotClaimed',None)!='FALSE':
                raise ValueError('Unresolved project state')
            result=context['active_projects'][project]
        elif kind=='LootConditionIsPlayerPersistentFlagValue':
            flag=tree.reference(props.pop('myPersistentFlag'))['uid']
            expected=props.pop('myValue','TRUE')
            if expected not in ('TRUE','FALSE'):raise ValueError('Unknown persistent flag value')
            result=context['flags'][flag]==(expected=='TRUE')
        elif kind=='LootConditionIsRoleElite':result=context['elite']
        elif kind=='LootConditionPlayerProgressionTier':
            if props.pop('myProgressionTier')!=context['progression_tier']:
                raise ValueError('Unresolved progression tier ordering')
            operator=props.pop('myOperator','GreaterThanOrEqual')
            result={'Equal':True,'GreaterThanOrEqual':True,'LessThanOrEqual':True,
                    'NotEqual':False,'GreaterThan':False,'LessThan':False}[operator]
        elif kind=='LootConditionIsInSkyscraperFloor':
            if props.pop('myOperator','GreaterThanOrEqual')!='GreaterThanOrEqual':raise ValueError('Unsupported floor operator')
            result=context['floor']>=int(props.pop('mySkyscraperFloor'))
        elif kind=='LootConditionLooterLevel':
            if props.pop('myXPType','NormalXP')!='NormalXP':raise ValueError('Unresolved level currency')
            op=props.pop('myOperator','GreaterThanOrEqual')
            level=int(props.pop('myLevel'))
            player=context['level']
            result={'Equal':player==level,'NotEqual':player!=level,'GreaterThan':player>level,
                    'GreaterThanOrEqual':player>=level,'LessThan':player<level,'LessThanOrEqual':player<=level}[op]
        elif kind=='LootConditionIsRoleNamed':result=context['named']
        elif kind=='LootConditionIsInSpecOp':result=context['spec_op']
        elif kind=='LootConditionIsMissionDifficulty':result=context['difficulty']==props.pop('myMissionDifficulty','Normal')
        elif kind=='LootConditionGlobalDifficulty':
            levels=('Normal','Hard','Challenge','Heroic')
            current=levels.index(context['global_difficulty']);required=levels.index(props.pop('myGlobalDifficulty','Normal'))
            result={'Equal':current==required,'NotEqual':current!=required,'LessThan':current<required,'GreaterThan':current>required,
                    'LessThanOrEqual':current<=required,'GreaterThanOrEqual':current>=required}[props.pop('myOperator','Equal')]
        elif kind=='LootConditionIsInMissionType':result=context['mission']==props.pop('myMissionType')
        elif kind=='LootConditionIsInCertainMission':result=context['mission_uid']==tree.reference(props.pop('mySelectedMission'))['uid']
        elif kind=='LootConditionOpenWorldProgressionTier':
            tiers=context['world_tiers']
            if props.pop('myOperator','Equal')!='GreaterThanOrEqual':raise ValueError('Unresolved world tier operator')
            result=tiers.index(context['world_tier'])>=tiers.index(props.pop('myProgressionTier'))
        elif kind=='LootConditionIsTargetedLootRotationSource':result=context['source']==props.pop('myTargetedLootRotationSource','AGENT')
        elif kind=='LootConditionIsLivingWorldSimulationSiteCurrentDefenceLevel':
            minimum,maximum=int(props.pop('myMinLevel')),int(props.pop('myMaxLevel'))
            result=minimum<=context['cp_level']<=maximum
        else:raise ValueError('Unresolved runtime condition: '+kind)
    if props:raise ValueError('Unresolved runtime condition properties')
    return not result if negated=='TRUE' else result


CONTEXTS=[dict(source='AGENT',named=False,spec_op=False,mission='None',cp_level=0,difficulty='Heroic',dark_zone=False),
          dict(source='AGENT',named=False,spec_op=False,mission='None',cp_level=0,difficulty='Challenge',dark_zone=True)]


def eligible(node,root,context):
    parents=ancestor_path(root,node)
    try:
        weight=float(tree.prop(node,'myDropWeight','100'))
        return (groups_allow_drop(parents) and isfinite(weight) and weight>0
                and all(permits(conditions(p),context) for p in parents))
    except (KeyError,ValueError):
        return False


def drop_branches(table,kind,context):
    for group in (tree.child(table,'myLootGroups') or {}).get('children',[]):
        if ' : ' in group['header']:continue
        listing=tree.child(group,'myLootItemList')
        for branch in listing['children'] if listing else []:
            if branch['header'].startswith(kind+' ') and ' : ' not in branch['header'] and eligible(branch,table,context):
                yield group,branch


def direct_drops(table,items,context,*,supports_prototype=None):
    targets=set()
    for group,branch in drop_branches(table,'LootItem',context):
        quality=tree.prop(branch,'myQualityChart') or tree.prop(group,'myQualityChart','')
        prototype=quality.endswith(' 1EAD798669A0257D0012BB21B6A3762A')
        targets.update(uid for uid,item in items.items() if item.get('obtainable') is True
                       and matches(branch,item['tags']) and (not prototype or supports_prototype and supports_prototype(uid)))
    return targets


def fixed_dungeon_quality(crafting, reference, quality):
    expected={'Exotic':'4CDCE5B25BE6DB97000330865A3EA4FE','GearSet':'075801E256B478E500000E3EB456DD10'}
    if not reference or not quality or quality not in expected:return False
    chart=tree.reference(reference)
    if chart['uid']!=expected[quality]:return False
    source='hunter/game system data/juice/loot/lootqualitycharts/'+chart['name'].lower()+'.mlootqualitychart'
    level_rows=tree.child(reference_nodes(crafting,source,chart['uid']),'myLootQualityChartList')
    levels=[n for n in level_rows['children'] if tree.prop(n,'myMinLevel')=='40'] if level_rows else []
    if len(levels)!=1 or tree.prop(levels[0],'myMinProgressionTier') not in (None,'WarlockLevel40'):return False
    elements=tree.child(levels[0],'myLootQualityChartElementList')
    rows=elements['children'] if elements else []
    return (len(rows)==1 and not rows[0]['children'] and tree.prop(rows[0],'myQuality')==quality
            and float(tree.prop(rows[0],'myDropChance','0'))==100)


def dungeon_drops(crafting, table, objects):
    """A shared loot tag or multiple eligible rolls has no established per-item rate."""
    rates = {}
    for group, branch in drop_branches(table, 'LootItem', {}):
        quality = tree.prop(branch, 'myQualityChart') or tree.prop(group, 'myQualityChart', '')
        if quality.endswith(' 1EAD798669A0257D0012BB21B6A3762A'):
            continue
        targets = [key for key, obj in objects.items() if obj.get('obtainable') is True and matches(branch, obj['tags'])]
        chance = None
        if (len(targets) == 1 and len(tree.child(group, 'myLootItemList')['children']) == 1
                and tree.prop(group, 'myUseQualityUnluckyStreaks') == 'FALSE'
                and tree.prop(group,'myHasLosersLuck','FALSE')=='FALSE'
                and all(tree.prop(branch,field,'1')=='1' for field in ('myMinItems','myMaxItems'))
                and not any(tree.child(group,field) or tree.prop(group,field) for field in ('myContamination','myBackupItemList'))
                and fixed_dungeon_quality(crafting,quality,objects[targets[0]].get('quality'))):
            chance = float(tree.prop(group, 'myDropChancePercentage', '100'))
        for target in targets:
            rates[target] = chance if target not in rates else None
    branches=[n for n in tree.walk(table) if n['header'].startswith('LootItem ')]
    for target,chance in rates.items():
        if chance is not None and sum(matches(b,objects[target]['tags']) for b in branches)!=1:
            rates[target]=None
    return rates


def dungeon_label(activity, action, chance):
    text = activity + ' - ' + action
    return text if chance is None else text + f' [{chance:g}%]'


def targeted(crafting, table, rows):
    generic=crafting.document(LOOT+'targetedloottable_generic.juice')
    definitions=crafting.document(LOOT+'conditionlists/conditionlist_targetedloot_common.juice')
    groups={name(n):n for n in generic['children'] if n['header'].startswith('LootGroup ')}
    condition_defs={name(n):n for n in definitions['children'] if n['header'].startswith('LootConditions ')}
    entries=[]
    for child in tree.walk(table):
        if not child['header'].startswith('LootGroup '):continue
        parent=groups.get(child['header'].split(' : ',1)[1].strip('"')) if ' : ' in child['header'] else child
        if not parent or tree.child(child,'myConditions'):continue
        reference=tree.prop(child,'myConditions',tree.prop(parent,'myConditions',''))
        condition=condition_defs.get(reference.removeprefix('= ').strip('"'))
        chance=float(tree.prop(child,'myDropChancePercentage',tree.prop(parent,'myDropChancePercentage','100')))
        modifier=tree.prop(child,'myDropChanceModifierAttribute',tree.prop(parent,'myDropChanceModifierAttribute'))
        if not condition or not 0<chance<=100 or modifier not in (None,'0'*32,'6F2AF9195F64996C00036B697C8CD4B5'):continue
        # Only branches that actually reference this table's item list qualify.
        itemlist=tree.prop(child,'myLootItemList','')
        if not itemlist.startswith('= '):continue
        for context in CONTEXTS:
            try:
                if not all(permits(conditions(n),context) for n in ancestor_path(table,child)[:-1]):continue
                if not permits(tree.semantic(condition),context):continue
            except (ValueError,KeyError):continue
            entries.append((context,itemlist,name(condition),name(child),name(parent)))
    for row in rows.values():
        row['entry_scope']='pool'
        witnesses=[]
        for context,itemlist,condition,child,parent in entries:
            if itemlist!='= '+row['item_list']+' 00000000000000000000000000000000':continue
            try:
                if not all(permits(n,context) for n in row['conditions']):continue
            except (ValueError,KeyError):continue
            witnesses.append({'context':context,'conditions':condition,'group':child,'parent':parent})
        if witnesses:
            row['entry_scope']='route';row['runtime_witnesses']=witnesses
            row['restriction']='dark_zone' if all(w['context']['dark_zone'] for w in witnesses) else ''


def common(crafting, collect):
    entry=LOOT+'ltdrp_npc_normal.mloottable'
    root=reference_nodes(crafting,entry,'075801E25AA6442700006594DA50847A')
    table_file=LOOT+'ltdrp_npc_normal_heroic.mloottable'
    table=reference_nodes(crafting,table_file,'075801E25E1C4C3100034FD80541ECCE')
    links=[n for n in tree.walk(root) if tree.prop(n,'myTable') and tree.reference(tree.prop(n,'myTable'))['uid']=='075801E25E1C4C3100034FD80541ECCE']
    if len(links)!=1:raise ValueError('NPC difficulty entry changed')
    context=CONTEXTS[0]
    parents=[conditions(n) for n in ancestor_path(root,links[0]) if conditions(n)]
    if not all(permits(n,context) for n in parents):raise ValueError('NPC entry conditions unresolved')
    groups=[n for n in tree.walk(table) if tree.prop(n,'myLootItemList')=='= ItemList_Main 00000000000000000000000000000000']
    if len(groups)!=1:raise ValueError('NPC equipment pool changed')
    group=groups[0]
    if float(tree.prop(group,'myDropChancePercentage','100'))<=0:raise ValueError('NPC equipment drop disabled')
    parents += [conditions(n) for n in ancestor_path(table,group) if conditions(n)]
    if not all(permits(n,context) for n in parents):raise ValueError('NPC pool conditions unresolved')
    source='hunter/game system data/rejuice/itemlist_main.rejuice'
    rows=collect('common_gear_pool',source,entry,'075801E25AA6442700006594DA50847A')
    for row in rows.values():
        row['parent_conditions']=parents;row['entry_scope']='pool'
        try:
            if all(permits(n,context) for n in row['conditions']):
                row['entry_scope']='route';row['runtime_witnesses']=[{'context':context,'table':table_file,'group':name(group)}]
        except (ValueError,KeyError):pass
    return rows
