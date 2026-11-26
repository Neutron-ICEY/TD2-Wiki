"""Reusable equipment pools, RewardItem targets and blueprint RewardLoot pools."""
import re
import hashlib
import math
from pathlib import PurePosixPath
from . import native_tree as tree
from .native_sources import matches, conditions, ancestor_path, reference_nodes, ITEM, LOOT
from .crafting import scalar


def uid(node):
    match=re.search(r'<\s*uid=([A-Fa-f0-9]{32})\s*>',node['header'])
    if not match: raise ValueError('Source entry UID unavailable')
    return match[1].upper()


def project(crafting, known, blueprints, records):
    # This restriction applies to native drop/vendor candidates only; absence or
    # FALSE does not assert that an item cannot be crafted or was never awarded.
    for identity,item in known.items():
        try: value=scalar(crafting.native,records[identity],'myIsObtainable','TRUE')=='TRUE'
        except (ValueError,KeyError,OSError): value=None
        crafting.unit(['items',identity,'obtainable'],value)
        item['obtainable']=value

    def collect(kind, source, entry, entry_uid, scope=None, context=None, objects=None, strict=False):
        document=crafting.document(source)
        container=document if scope is None else next(n for n in tree.walk(document) if n['header'].startswith(scope))
        result={}
        for node in tree.walk(container):
            if not node['header'].startswith('LootItem ') or float(tree.prop(node,'myDropWeight','100'))<=0:continue
            if any(float(tree.prop(p,'myDropChancePercentage','100'))<=0 or float(tree.prop(p,'myDropWeight','100'))<=0 for p in ancestor_path(document,node)):continue
            targets=sorted(u for u,item in (known if objects is None else objects).items() if item.get('obtainable') is not False and matches(node,item['tags']))
            if not targets:continue
            if strict:
                from .native_sources import groups_allow_drop
                parents=ancestor_path(document,node)
                if not math.isfinite(float(tree.prop(node,'myDropWeight','100'))):raise ValueError('Invalid loot item weight')
                if any(' : ' in p['header'] for p in parents):raise ValueError('Unresolved source inheritance')
                if not groups_allow_drop(parents):continue
            definition=tree.semantic(node)
            parents=ancestor_path(document,node)
            gates=[conditions(n) for n in parents if conditions(n)]
            chances=[tree.prop(n,'myDropChancePercentage','100') for n in parents if n['header'].startswith('LootGroup ')]
            # Identical branches deduplicate; editor object labels and order do
            # not form identities. Reader relations group by entry and target.
            digest=hashlib.sha256(repr((definition,gates,chances)).encode()).hexdigest()[:20]
            result[kind+':'+entry_uid+':'+digest]={'kind':kind,'entry':entry,'entry_uid':entry_uid,'source':source,
                'targets':targets,'conditions':gates,
                'definition':definition,'context_refs':context or [],'verification':'native_only'}
            if scope=='LootItemList ':result[kind+':'+entry_uid+':'+digest]['item_list']=container['header'].split(' ',1)[1]
        return result
    try:
        source=ITEM+'sealed_cache_season_named_item.mitem'
        entry=next(n for n in tree.walk(crafting.document(source)) if n['header'].startswith('BundleItem '))
        ref=next(tree.reference(tree.prop(n,'myLootTable')) for n in tree.walk(entry) if tree.prop(n,'myLootTable'))
        table=LOOT+ref['name'].lower()+'.mloottable';reference_nodes(crafting,table,ref['uid'])
        rows=collect('named_cache',table,source,uid(entry))
        for row in rows.values():
            row['text']='开启'+crafting.text(tree.prop(entry,'myUIName'))
            row['parent_conditions']=[conditions(entry)] if conditions(entry) else []
        crafting.unit(['routes','named_cache'],rows)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('named_cache',error)
    try:
        source='hunter/interaction/settings/interact_loot_table_equipment_special_haven.minteractionsetup'
        entry=reference_nodes(crafting,source,'075801E25DDBE50F000353E702AD6847')
        reward=tree.child(entry,'myRewardSettings < uid=075801E25DDBE50F000353EB2444665B >')
        ref=tree.reference(tree.prop(reward,'myLootTable'))
        table=LOOT+ref['name'].lower()+'.mloottable'
        reference_nodes(crafting,table,ref['uid'])
        rows=collect('hunter_cache',table,source,uid(entry))
        for row in rows.values():row['interaction']=tree.semantic(entry)
        # The dye is the persistent unlock checked by both merchants.
        dye_source=ITEM+'dye_camo_base_09_full.mitem'
        dye=reference_nodes(crafting,dye_source,'B1046E3B5E2C604F000644D453DA8CBD')
        dye_tags=tree.tags(dye,'myTags')
        if not any(matches(n,dye_tags) for n in tree.walk(crafting.document(table)) if n['header'].startswith('LootItem ')):
            raise ValueError('Hunter box unlock reward changed')
        crafting.unit(['source_contexts','hunter_cache'],{'unlock_items':[uid(dye)],'source':dye_source,'interaction':tree.semantic(entry)})
        crafting.unit(['routes','hunter_cache'],rows)
        vendor_source='hunter/game system data/juice/vendors/vendor configs/hun_vendor_roaming.mvendorconfig'
        vendor=reference_nodes(crafting,vendor_source,'BFADE5F95BBC98590003071AC4EF34F3')
        vendor_ref=tree.reference(tree.prop(vendor,'myLootTable'))
        vendor_table=LOOT+vendor_ref['name'].lower()+'.mloottable'
        reference_nodes(crafting,vendor_table,vendor_ref['uid'])
        candidates=collect('hunter_vendor',vendor_table,vendor_source,uid(vendor))
        targets={t for row in rows.values() for t in row['targets']}
        selected={}
        for key,row in candidates.items():
            row['targets']=[t for t in row['targets'] if t in targets]
            if row['targets'] and 'myRequiredItemType dye_camo_base_09_full' in str(row['conditions']):selected[key]=row
        crafting.unit(['routes','hunter_vendor'],selected)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('hunter_cache',error)
    try:
        from .native_drop_sources import common
        rows=common(crafting,collect)
        crafting.unit(['routes','common_gear_pool'],rows)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('common_gear_pool',error)
    def rotation_routes(kind, category, objects):
        rotation='hunter/game system data/juice/loot/targetedlootrotationpools.juice'
        rotation_doc=crafting.document(rotation)
        context={source:tree.semantic(crafting.document(source)) for source in
            [LOOT+'targetedloottable_generic.juice',LOOT+'conditionlists/conditionlist_targetedloot_common.juice']}
        shared=list(context)
        rows={}
        entries=[n for n in rotation_doc['children'] if n['header'].startswith('TargetedLootPool ') and tree.prop(n,'myCategory')==category]
        if not entries:raise ValueError('Missing targeted loot rotation: '+category)
        for entry in entries:
            ref=tree.reference(tree.prop(entry,'myLootTable'))
            source=LOOT+ref['name'].lower()+'.mloottable'
            table=reference_nodes(crafting,source,ref['uid'])
            # Keep the rotation gates and the exact ordinary item list. Prototype-only lists
            # are separate pools with additional quality and difficulty requirements.
            context[uid(table)]=tree.semantic(table)
            context[uid(entry)]=tree.semantic(entry)
            matched=collect(kind,source,rotation,uid(table),'LootItemList ',shared+[uid(table)],objects=objects)
            from .native_drop_sources import targeted
            targeted(crafting,table,matched)
            for row in matched.values():
                row['slot']=ref['name'].rsplit('_',1)[-1].lower()
                row['rotation_uid']=uid(entry)
                row['warlock_completed']=tree.prop(entry,'myIsForWarlockCompleted','FALSE')=='TRUE'
            rows.update(matched)
        crafting.unit(['source_contexts',kind],context)
        crafting.unit(['routes',kind],rows)
    if any(i.get('collection')!='武器型号资料' for i in known.values()):
        for kind,category in [('targeted_slot','GearType'),('targeted_brand','Brand'),('targeted_gearset','Gearset')]:
            try:rotation_routes(kind,category,known)
            except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing(kind,error)
    weapons={u:i for u,i in known.items() if i.get('collection')=='武器型号资料' and i['slot']!='SignatureWeapon'}
    if weapons:
        try:
            rotation_routes('targeted_weapon','WeaponType',weapons)
        except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('targeted_weapon',error)
    from .weapon_reward_sources import project as weapon_rewards
    from .native_blueprint_rewards import (blueprint_index, journey_blueprints, progression_blueprints, retaliation,
                                          season_blueprints, legacy_manhunts, mission_boss_blueprints, mission_cache_blueprints)
    weapon_rewards(crafting,weapons,blueprints,known)
    try:retaliation(crafting,blueprints)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('retaliation_blueprint',error)
    try:legacy_manhunts(crafting)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('legacy_manhunts',error)
    try:mission_boss_blueprints(crafting,blueprints)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('mission_boss_blueprint',error)
    try:crafting.unit(['routes','mission_cache_blueprint'],mission_cache_blueprints(crafting,blueprints))
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('mission_cache_blueprint',error)
    for kind,collect_recipes in [('progression_blueprint',progression_blueprints),('journey_blueprint',journey_blueprints)]:
        try:collect_recipes(crafting,blueprint_index(blueprints))
        except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing(kind,error)

    try:
        objects={**known,**blueprints};byfile={}
        for identity,item in objects.items():byfile.setdefault(item['source'].lower(),[]).append(identity)
        rows={};files=[]
        for namespace in ('hunter','rogue'):
            directory=crafting.native.file(namespace+'/game system data/juice/rewards')
            if not directory.is_dir():raise ValueError('Reward directory missing: '+namespace)
            files.extend(sorted(directory.rglob('*.mreward')))
        if not files:raise ValueError('Reward export unavailable')
        for file in files:
            text=file.read_text('utf-8-sig')
            if 'myItemTypeFile' not in text:continue
            source=file.relative_to(crafting.native.root).as_posix();doc=tree.parse(text)
            for node in tree.walk(doc):
                value=tree.prop(node,'myItemTypeFile')
                if not value:continue
                target=value.strip('"')
                if target.startswith('./'):target=str(PurePosixPath(source).parent/target)
                ids=byfile.get(target.lower(),[])
                if not ids:continue
                parents=ancestor_path(doc,node)
                reward=next(n for n in parents if re.search(r'<\s*uid=',n['header']))
                key='direct_reward:'+uid(reward)
                row=rows.setdefault(key,{'kind':'direct_reward','entry':source,'entry_uid':uid(reward),'source':source,
                    'targets':[],'definition':tree.semantic(reward),'entry_scope':'reward_object','verification':'native_only'})
                row['targets']=sorted(set(row['targets']+ids))
        crafting.unit(['routes','direct_reward'],rows)
    except (ValueError,KeyError,OSError,StopIteration,UnicodeError) as error:crafting.missing('direct_reward',error)
    else:
        try:season_blueprints(crafting,blueprints,rows)
        except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('season_blueprint',error)
    try:
        rows={}
        from .native_special_sources import DIFFICULTIES, blueprint_triggers, reward_difficulties, summit_challenge_grants
        for filename,title in [('rwref_lws_controlpoint_loot.mreward','控制点奖励'),('rwref_proj_weekly_blueprint.mreward','计划奖励')]:
            source='hunter/game system data/juice/rewards/'+filename
            reward=next(n for n in tree.walk(crafting.document(source)) if n['header'].startswith('RewardLoot '))
            ref=tree.reference(tree.prop(reward,'myLootTable'))
            table=LOOT+ref['name'].lower()+'.mloottable';pool=reference_nodes(crafting,table,ref['uid'])
            selected=collect('blueprint_reward_pool',table,source,uid(reward),scope=pool['header'],objects=blueprints,strict=True)
            label,witnesses=blueprint_triggers(crafting,uid(reward),control_point=filename=='rwref_lws_controlpoint_loot.mreward')
            unrestricted=reward_difficulties(reward)==set(DIFFICULTIES)
            if not unrestricted:witnesses=[]
            for row in selected.values():
                row['entry_scope']='reward_object';row['text']=title
                row['reward_definition']=tree.semantic(reward)
                if witnesses:
                    row.update(entry_scope='route',display_text=label,runtime_witnesses=witnesses)
            if filename=='rwref_proj_weekly_blueprint.mreward':
                try:
                    summit=summit_challenge_grants(crafting,uid(reward),selected) if unrestricted else {}
                    crafting.unit(['routes','summit_challenge_blueprint'],summit)
                except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('summit_challenge_blueprint',error)
            rows.update(selected)
        crafting.unit(['routes','blueprint_reward_pool'],rows)
    except (ValueError,KeyError,OSError,StopIteration) as error:crafting.missing('blueprint_reward_pool',error)
    from .native_special_sources import project as special_sources
    special_sources(crafting,collect,known,records,blueprints)
    names=set()
    def visit(value):
        if isinstance(value,dict):
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
        elif isinstance(value,str) and value.startswith('myRequiredItemType '):names.add(value.split(' ',1)[1])
    for unit in crafting.units:
        if unit['path'][0]=='routes':visit(unit['value'])
    for name in sorted(names):
        try:
            candidates=[]
            for namespace in ('hunter','rogue'):
                source=namespace+'/game system data/juice/item/'+name.lower()+'.mitem'
                if not crafting.native.file(source).is_file():continue
                for node in tree.walk(crafting.document(source)):
                    if node['header'].split(' ',1)[-1].split(' <')[0].split(' : ')[0].strip('"').lower()==name.lower():candidates.append((source,node))
            if len(candidates)!=1:raise ValueError('Required item identity unavailable')
            source,node=candidates[0];value=tree.prop(node,'myUIName')
            if not value and node['header'].startswith('CraftingBlueprintItem '):
                target=tree.reference(tree.prop(node,'myCraftedItem'))['uid']
                label=crafting.native.text(records[target],'myUIName')+'制作图纸'
            elif not value and uid(node) in records:
                label=crafting.native.text(records[uid(node)],'myUIName')
            else:label=crafting.text(value)
            crafting.unit(['condition_items',name],{'uid':uid(node),'name':label,'source':source})
        except (ValueError,KeyError,OSError) as error:crafting.missing('source-condition:'+name,error)
