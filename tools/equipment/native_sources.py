"""Follow registered native entry points; candidate routes never imply live availability."""
import re
import hashlib
from pathlib import PurePosixPath
from . import native_tree as tree
from .crafting import links

ITEM='hunter/game system data/juice/item/'
LOOT='hunter/game system data/juice/loot/loottables/'
VENDOR='hunter/game system data/juice/vendors/vendor configs/hun_vendor_crafting_boo.mvendorconfig'
PROJECTS='hunter/game system data/juice/projects/projectsseasonaljourney.juice'


def loot_tags(node,field):
    block=tree.child(node,field)
    if not block:return []
    # Native flat lists are OR; every LootTagsAND is one conjunction in that OR.
    result=[[tag] for tag in tree.tags(node,field)]
    for group in block['children']:
        if not group['header'].startswith('LootTagsAND '):raise ValueError('Unknown loot tag operation')
        wrapped={'children':[dict(group,header=field)]}
        result.append(tree.tags(wrapped,field))
    return result


def matches(node,tags):
    include=loot_tags(node,'myIncludeTags')+loot_tags(node,'myIncludeLootTags')
    exclude=loot_tags(node,'myExcludeTags')+loot_tags(node,'myExcludeLootTags')
    return bool(include) and any(all(t in tags for t in group) for group in include) and not any(all(t in tags for t in group) for group in exclude)


def conditions(node):
    block=tree.child(node,'myConditions')
    reference=tree.prop(node,'myConditions')
    if reference:return {'type':'NativeConditionReference','properties':[reference],'children':[]}
    return tree.semantic(block) if block else None


def ancestor_path(root,target):
    if root is target:return [root]
    for child in root['children']:
        path=ancestor_path(child,target)
        if path:return [root]+path
    return []


def groups_allow_drop(parents):
    for node in parents:
        if not node['header'].startswith('LootGroup '):continue
        if tree.prop(node,'myDropChanceModifierAttribute') not in (None,'0'*32):
            raise ValueError('Loot group probability modifier unresolved')
        # LootGroup defaults to 100; a disabled parent cannot yield a positive-weight item.
        chance=float(tree.prop(node,'myDropChancePercentage','100'))
        if not 0<=chance<=100:raise ValueError('Invalid loot group probability')
        if chance==0:return False
    return True


def reference_nodes(crafting,source,uid):
    found=[n for n in tree.walk(crafting.document(source)) if re.search(r'<\s*uid='+re.escape(uid)+r'\s*>',n['header'],re.I)]
    if len(found)!=1:raise ValueError('Missing or ambiguous route UID: '+uid)
    return found[0]


def project(crafting,known,blueprints,blueprint_records):
    routes={}
    def stable(*labels):return hashlib.sha256('\n'.join(labels).encode()).hexdigest()[:20]
    def node_key(node):
        refs=re.findall(r'<\s*uid=([A-Fa-f0-9]{32})', '\n'.join(p for p,_ in node['properties']))
        return refs[0] if refs else node['header']
    def route(identity,data):
        if identity in routes:
            if routes[identity]==data:return
            identity+=':'+str(sum(k.startswith(identity) for k in routes))
        routes[identity]=data

    # The entitlement grants the conversion blueprint. The weapon in the
    # same pack is a different item from the endgame recipe's output.
    for name,conversion,pack_uid in (
            ('ruthless','4CDCE5B25C125A4700032042322ABAD4','2762CD105CAB1909000337A5EE3E2786'),
            ('lullaby','4CDCE5B25C125A5A00032047378F37E0','2762CD105CAB18ED000337A458734B20')):
        if conversion not in blueprints:continue
        kind=name+'_pack'
        try:
            pack_source='hunter/game system data/juice/vanity/itempacks/'+name+'weaponpack.mvanityitempack'
            grant_source='hunter/game system data/juice/firstpartystore/itempacks.juice'
            native=crafting.native
            pack=native.record(pack_source,pack_uid)
            grant_ref,=links(native,pack,'myFirstPartyItemPack')
            grant_uid=grant_ref['target_uid']
            grant=native.record(grant_source,grant_uid)
            listed,granted=[conversion in {r['target_uid'] for r in links(native,item,'myItems')} for item in (pack,grant)]
            if listed!=granted:raise ValueError('Conversion blueprint differs between the listing and grant')
            rows={grant_uid:{'kind':kind,'entry':pack_source,'entry_uid':grant_uid,'source':grant_source,
                             'targets':[conversion],'verification':'native_only'}} if granted else {}
            crafting.unit(['routes',kind],rows)
        except (ValueError,KeyError,OSError) as error:crafting.missing(kind,error)

    # The cache entry must still reference the exact table; a matching tag alone
    # elsewhere in the dump is insufficient evidence for this route.
    for label,source,table,table_uid,targets in (
        ('reconstructed_cache',ITEM+'sealed_cache_sd_nemesis9_defeat.mitem',LOOT+'ltdrp_sealed_cache_sd_nemesis9_defeat.mloottable','FB6E28D2643FE7A5000720187D9D4F14',blueprints),
        ('exotic_cache',ITEM+'sealed_cache_season_exotic_item.mitem',LOOT+'ltdrp_sealed_cache_exotic_item.mloottable','83ED36DA5E172C4B000353E3FB01798A',known)):
        try:
            entry=crafting.document(source);entry_links=[n for n in tree.walk(entry) if tree.prop(n,'myLootTable') and tree.reference(tree.prop(n,'myLootTable'))['uid']==table_uid]
            if len(entry_links)!=1:raise ValueError('Cache table reference changed or ambiguous')
            entry_scopes=ancestor_path(entry,entry_links[0])
            table_node=reference_nodes(crafting,table,table_uid)
            itemlist='hunter/game system data/rejuice/itemlist_exotics_all.rejuice' if label=='exotic_cache' else table
            list_scopes=[]
            if label=='exotic_cache':
                refs=[n for n in tree.walk(table_node) if any(re.search(r'=\s*itemlist_exotics_all\s',p,re.I) for p,_ in n['properties'])]
                if len(refs)!=1:raise ValueError('Exotic item list reference changed or ambiguous')
                list_scopes=ancestor_path(table_node,refs[0])
            for number,node in enumerate(tree.walk(crafting.document(itemlist))):
                if not node['header'].startswith('LootItem '):continue
                ids=sorted(uid for uid,item in targets.items() if matches(node,item['tags']))
                if not ids:continue
                parents=entry_scopes+list_scopes+ancestor_path(crafting.document(itemlist),node)[:-1]
                if float(tree.prop(node,'myDropWeight','100'))<=0:continue
                bundle=next(n for n in entry_scopes if n['header'].startswith('BundleItem '))
                value={'kind':label,'entry':source,'entry_uid':re.search(r'uid=([A-Fa-f0-9]{32})',bundle['header'])[1].upper(),'table':table,'source':itemlist,'targets':ids,'conditions':conditions(node),
                       'parent_conditions':[conditions(p) for p in parents if conditions(p)],
                       'definition':tree.semantic(node),'verification':'native_only'}
                if not groups_allow_drop(parents):value['entry_scope']='disabled'
                # UIDs form stable identities even if editor labels/order change.
                identity=label+':'+stable(node['header'],node_key(node))
                route(identity,value)
        except (ValueError,KeyError,OSError) as error:crafting.missing(label,error)

    try:
        vendor=next(n for n in tree.walk(crafting.document(VENDOR)) if n['header'].startswith('VendorConfig '))
        link=tree.reference(tree.prop(vendor,'myLootTable'));source=LOOT+link['name'].lower()+'.mloottable'
        table=reference_nodes(crafting,source,link['uid'])
        for group in tree.walk(table):
            if not group['header'].startswith('LootGroup '):continue
            for node in tree.walk(group):
                if not node['header'].startswith('LootItem '):continue
                ids=sorted(uid for uid,b in blueprints.items() if matches(node,b['tags']))
                if not ids or float(tree.prop(node,'myDropWeight','100'))<=0:continue
                value={'kind':'vendor','entry':VENDOR,'entry_uid':re.search(r'uid=([A-Fa-f0-9]{32})',vendor['header'])[1].upper(),'source':source,'targets':ids,
                      'conditions':{'group':conditions(group),'item':conditions(node)},'definition':tree.semantic(node),
                      'restock':tree.prop(vendor,'myGameScheduleForRestock'),'verification':'native_only'}
                # Keep the denied target so a generic source hint cannot restore vendor availability.
                if not groups_allow_drop(ancestor_path(table,node)[:-1]):value['entry_scope']='disabled'
                route('vendor:'+link['uid']+':'+stable(group['header'],node['header'],node_key(node)),value)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('crafting_vendor',error)

    # Project -> objective -> reward UID -> RewardItem file -> blueprint UID.
    try:
        projects=[n for n in tree.walk(crafting.document(PROJECTS)) if n['header'].startswith('Project ')]
        for project in projects:
            project_uid=re.search(r'uid=([A-Fa-f0-9]{32})',project['header'])[1]
            for objective in tree.walk(project):
                raw=tree.prop(objective,'myCompletionReward')
                if not raw or re.fullmatch(r'<\s*uid=[A-Fa-f0-9]{32}\s*>\s*=\s*NULLREFERENCE',raw):continue
                link=tree.reference(raw);source='hunter/game system data/juice/rewards/'+link['name'].lower()+'.mreward'
                if not crafting.native.file(source).is_file():raise ValueError('Project reward file missing: '+source)
                # An incomplete scan cannot replace the previous relation group.
                reward=reference_nodes(crafting,source,link['uid'])
                ids=[]
                for node in tree.walk(reward):
                    item=tree.prop(node,'myItemTypeFile')
                    if not item:continue
                    path=item.strip('"')
                    if path.startswith('./'):path=str(PurePosixPath(source).parent/path)
                    found=[r for r in blueprint_records if r['_source'].lower()==path.lower() and r['resource_uid'] in blueprints]
                    ids.extend(r['resource_uid'] for r in found)
                if not ids:continue
                route('reward:'+project_uid+':'+link['uid'],{'kind':'project_reward','entry':PROJECTS,'project_uid':project_uid,'reward_uid':link['uid'],
                      'source':source,'targets':sorted(set(ids)),'objective':tree.semantic(objective),'verification':'native_only'})
    except (ValueError,KeyError,OSError,TypeError) as error:crafting.missing('project_rewards',error)
    for kind in ('reconstructed_cache','exotic_cache','vendor','project_reward'):
        # The complete relation group replaces its previous membership; obsolete
        # tag matches must not linger as separate, never-deleted route records.
        relevant={k:v for k,v in routes.items() if v['kind']==kind}
        blocked={'reconstructed_cache':'reconstructed_cache','exotic_cache':'exotic_cache','vendor':'crafting_vendor','project_reward':'project_rewards'}[kind]
        if not any(r.get('target')==blocked for r in crafting.unavailable):crafting.unit(['routes',kind],relevant)
    return routes
