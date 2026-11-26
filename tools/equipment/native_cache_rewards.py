"""Cache suppliers and their equipment contents, joined by native object identity."""
from functools import lru_cache
from pathlib import PurePosixPath
from . import native_tree as tree
from .crafting import scalar
from .native_drop_sources import direct_drops, eligible
from .native_sources import matches, reference_nodes
from .native_source_rules import uid
from .native_special_sources import DIFFICULTIES, referenced, reward_difficulties


def progression_supply(crafting,caches,supplies):
    source='hunter/game system data/rejuice/progression_rewards_data.rejuice'
    unresolved=[]
    groups={}
    for path in dict.fromkeys(crafting.native.includes(source)):
        if not path.endswith('.mreward') or not crafting.native.file(path).is_file():continue
        for node in crafting.document(path)['children']:
            if node['header'].startswith('RewardGroup '):groups.setdefault(uid(node),[]).append((path,node))
    for track in tree.walk(crafting.document(source)):
        xp=tree.prop(track,'myXPType')
        if xp not in ('OrganizedPvpXP','PostDarkZoneCapProficiencyXP','WarlockInfinitePowerXP'):continue
        for rule in (tree.child(track,'myRulesList') or {}).get('children',[]):
            period=int(tree.prop(rule,'myRewardInterval','1'))
            low=int(tree.prop(rule,'myMinLevelRange','1'))
            high=int(tree.prop(rule,'myMaxLevelRange','-1'))
            if period<1 or high!=-1 and high<low or float(tree.prop(rule,'myRewardWeight','1'))<=0:continue
            raw=tree.prop(rule,'myRewardAsset')
            if not raw or raw.endswith('NULLREFERENCE'):continue
            try:
                (group_file,group),=groups.get(tree.reference(raw)['uid'],[])
                if reward_difficulties(group)!=set(DIFFICULTIES):continue
            except (ValueError,OSError,KeyError) as error:
                unresolved.append(dict(xp=xp,reward=tree.reference(raw),reason=str(error)))
                continue
            for leaf in (tree.child(group,'myRewards') or {}).get('children',[]):
                if not leaf['header'].startswith('RewardLoot '):continue
                try:valid=reward_difficulties(leaf)
                except ValueError:continue
                if valid!=set(DIFFICULTIES):continue
                try:table_file,table=referenced(crafting,tree.prop(leaf,'myLootTable'),'loot/loottables','.mloottable')
                except (ValueError,OSError) as error:
                    unresolved.append(dict(xp=xp,group=group_file,leaf=uid(leaf),reason=str(error)))
                    continue
                for target in direct_drops(table,caches,{'level':40}):
                    if caches[target]['key_required']:continue
                    supplies[target].append(dict(xp=xp,levels=[low,high],interval=period,progression=source,
                        group=group_file,leaf_uid=uid(leaf),table=table_file,table_uid=uid(table)))
    crafting.unit(['source_contexts','progression_cache_gaps'],unresolved)


def regular_cache_contents(crafting,items,caches,supplies,special):
    rows={}
    missing=[]
    context={'level':40,'progression_tier':'WarlockLevel40'}

    @lru_cache(maxsize=None)
    def includes(source,extension):
        return [p for p in crafting.native.includes(source) if p.endswith(extension)]

    @lru_cache(maxsize=None)
    def qualities(quality_uid,files):
        for path in files:
            for chart in crafting.document(path)['children']:
                if not chart['header'].startswith('LootQualityChart ') or uid(chart)!=quality_uid:continue
                levels=tree.child(chart,'myLootQualityChartList')
                eligible_levels=[n for n in levels['children'] if int(tree.prop(n,'myMinLevel','1'))<=40]
                if not eligible_levels:return set()
                level=max(eligible_levels,key=lambda n:int(tree.prop(n,'myMinLevel','1')))
                if tree.prop(level,'myMinProgressionTier') not in (None,'WarlockLevel40'):return set()
                return {tree.prop(n,'myQuality') for n in (tree.child(level,'myLootQualityChartElementList') or {}).get('children',[])
                        if float(tree.prop(n,'myDropChance','0'))>0}
        return set()

    @lru_cache(maxsize=None)
    def valid_qualities(target):
        item=items[target]
        native=crafting.native.record(item['source'],target)
        member=crafting.native.member(native,'myValidQualities')
        values={p['raw_value'] for p in (member or {}).get('properties',[]) if p.get('value_type')=='ItemQuality'
                and len(p['context'])==2 and p['context'][1]['resource_type']=='myValidQualities'}
        return values or {item['quality']}

    for identity,cache in caches.items():
        if not supplies[identity] or identity in special:continue
        try:
            source=cache['source']
            native=crafting.native.record(source,identity)
            if int(scalar(crafting.native,native,'myNumberOfGuaranteedItems','0'))<1:continue
            if int(scalar(crafting.native,native,'myMaxNumberOfLootItems','0'))<1:continue
            if crafting.native.member(native,'myPredeterminedItems'):continue
            slots=None
            for member in crafting.native.lineage(native):
                bundle=reference_nodes(crafting,member['_source'],member['resource_uid'])
                slots=tree.child(bundle,'myLootTables')
                if slots is not None:break
            if slots is None:continue
            # BundleLootTable has only a table pointer and a preview switch. Its editor name is immaterial.
            # Use the first guaranteed roll. Additional bonus rolls may have separate prerequisites.
            first=next(iter(slots['children']),None)
            if not first or not first['header'].startswith('BundleLootTable '):continue
            table_file,table=referenced(crafting,tree.prop(first,'myLootTable'),'loot/loottables','.mloottable')
            label=crafting.native.text(native,'myUIName')
            for index,group in enumerate((tree.child(table,'myLootGroups') or {}).get('children',[])):
                if ' : ' in group['header'] or not eligible(group,table,context):continue
                pool=tree.child(group,'myLootItemList')
                list_file=table_file
                if pool is None:
                    ref=tree.prop(group,'myLootItemList','').split()
                    if len(ref)!=3 or ref[0]!='=' or ref[-1]!='0'*32:continue
                    sources=[p for p in includes(table_file,'.rejuice') if PurePosixPath(p).stem.casefold()==ref[1].casefold()]
                    if len(sources)!=1:continue
                    list_file=sources[0]
                    pool=next((n for n in crafting.document(list_file)['children'] if n['header'].casefold()=='lootitemlist '+ref[1].casefold()),None)
                    if pool is None:continue
                targets=set()
                for branch in pool['children']:
                    if not branch['header'].startswith('LootItem ') or ' : ' in branch['header'] or not eligible(branch,pool,context):continue
                    raw=tree.prop(branch,'myQualityChart') or tree.prop(group,'myQualityChart')
                    if not raw or raw.endswith('NULLREFERENCE'):continue
                    files=tuple(dict.fromkeys(includes(list_file,'.mlootqualitychart')+includes(table_file,'.mlootqualitychart')))
                    q=qualities(tree.reference(raw)['uid'],files)
                    targets.update(t for t,i in items.items() if i.get('obtainable') is True and matches(branch,i['tags']) and q & valid_qualities(t))
                if targets:
                    rows[identity+':'+str(index)]=dict(kind='regular_cache',entry=source,entry_uid=identity,source=table_file,
                        table_uid=uid(table),item_list=list_file,targets=sorted(targets),runtime_witnesses=[context],
                        display_text=label,verification='native_only')
        except (OSError,ValueError,KeyError) as error:
            missing.append({'uid':identity,'source':cache['source'],'reason':str(error)})
    crafting.unit(['routes','regular_cache'],rows)
    crafting.unit(['source_contexts','bundle_inventory'],{'bundles':{k:dict(source=v['source'],key_required=v['key_required']) for k,v in caches.items()},
                                                          'unresolved_contents':missing})
