"""UID relations and native crafting economics, projected through the importer."""
import csv
import json
import re
import subprocess
from decimal import Decimal
from pathlib import Path
from . import native_tree as tree

CATALOG='data/equipment/crafting.json'
CRAFT='hunter/game system data/juice/crafting/crafting_definitions.juice'
DECON='hunter/game system data/juice/crafting/deconstruction_definitions.juice'
CURRENCIES='hunter/game system data/juice/currencies/currencies.rejuice'
SLOTS={'Mask':'mask','Chest':'chest','Holster':'holster','Backpack':'backpack','Gloves':'gloves','Kneepads':'kneepads'}
EQUIPMENT_SLOTS={'Face':'mask','Chest':'chest','Thighs':'holster','Back':'backpack','Hands':'gloves','Knees':'kneepads'}


def scalar(native,record,field,default=None):
    for row in native.lineage(record):
        values=[p['raw_value'] for p in row['properties'] if p['field']==field and len(p['context'])==1]
        if len(values)>1:raise ValueError('Duplicate item property: '+field)
        if values:return values[0]
    return default


def links(native,record,field):
    for row in native.lineage(record):
        doc=native.document(row['_source']);index=doc['resources'].index(row)
        found=[l for l in doc['links'] if l['source_index']==index and
               (len(l['context'])==1 and l['field']==field or len(l['context'])==2 and l['context'][1]['resource_type']==field)]
        if found:return found
        if any(e['field']==field and len(e['context'])==1 for e in row.get('empty_blocks',[])):return []
    return []


def item_tags(native,record):
    for row in native.lineage(record):
        found=[p['raw_value'] for p in row['properties'] if p.get('value_type')=='ItemTag' and len(p['context'])==2 and p['context'][1]['resource_type']=='myTags']
        if found:return sorted(set(found))
        if any(e['field']=='myTags' for e in row.get('empty_blocks',[])):return []
    return []


def formula(node):
    return {k:str(Decimal(tree.prop(node,'my'+k,'0.0'))) for k in ('A','B','C')}


def bracket_amount(rows,item_level=40,power=None):
    """Only use known level enums. Power is not interchangeable with item level."""
    def level(value):
        match=re.fullmatch(r'(?:Warlock)?Level(\d+)',value)
        if not match:raise ValueError('Unknown progression tier: '+value)
        return int(match[1])
    selected=[r for r in rows if level(r['min_level'])<=item_level]
    if not selected:raise ValueError('No matching currency bracket')
    selected=sorted(selected,key=lambda r:level(r['min_level']))
    if len(selected)>1 and selected[-1]['min_level']==selected[-2]['min_level']:raise ValueError('Ambiguous currency bracket')
    f=selected[-1];a,b,c=(Decimal(f[k]) for k in ('A','B','C'))
    if power is None and (a or b):raise ValueError('Native crafting power required')
    p=Decimal(str(power or 0));value=a*p*p+b*p+c
    if value<0 or value!=value.to_integral():raise ValueError('Native quantity rounding unresolved')
    return int(value)


def currency_requirement(node):
    ref=tree.reference(tree.prop(node,'myCurrencyDefinition'))
    rows=[{**formula(c),'min_level':tree.prop(c,'myMinItemLevel','Level1')} for c in tree.walk(node) if c['header'].startswith('BracketedCraftingValueFormula ')]
    if not rows:raise ValueError('Missing native currency formula')
    return {'currency_uid':ref['uid'],'brackets':rows}


def requirements(catalog,blueprint_uid,quality=None,item_level=40,power=None):
    """Evaluate a stated bench profile, never guess quality or substitute level for Power."""
    blueprint=catalog['blueprints'][blueprint_uid]
    quality=blueprint.get('quality_override') or quality
    if not quality:raise ValueError('Crafting bench quality required')
    if Decimal(str(item_level))>Decimal(blueprint['max_level']):raise ValueError('Blueprint maximum item level exceeded')
    amounts={}
    for tag in blueprint['tags']:
        rule=catalog.get('crafting_rules',{}).get(tag)
        if rule is None:continue
        if quality not in rule['qualities']:raise ValueError('Crafting quality unavailable: '+tag+' / '+quality)
        for row in rule['qualities'][quality]:
            uid=row['currency_uid'];amounts[uid]=amounts.get(uid,0)+bracket_amount(row['brackets'],item_level,power)
    item_rules=[catalog['item_requirements'][tag] for tag in blueprint['tags'] if tag in catalog.get('item_requirements',{})]
    if len(item_rules)>1:raise ValueError('Most-specific item requirement is not uniquely resolved')
    selected=[]
    if item_rules:
        qualities=next((c for c in item_rules[0]['children'] if c['type']=='myQualityDefinitions'),None)
        if qualities is None:raise ValueError('Missing item requirement qualities')
        def prop(node,key,default=None):
            found=[s[len(key)+1:] for s in node['properties'] if s.startswith(key+' ')]
            if len(found)>1:raise ValueError('Duplicate item requirement member')
            return found[0] if found else default
        rows=[r for r in qualities['children'] if prop(r,'myQuality','Grey')==quality]
        if len(rows)!=1:raise ValueError('Item requirement quality unavailable')
        # Keep item tags, quality mappings and min/max Power expressions intact;
        # their runtime filtering is separate from the additive currency total.
        selected=rows[0]['children']
    return {'profile':{'item_level':item_level,'quality':quality,'power':power},'currencies':amounts,'item_requirements':selected,'conditions':blueprint.get('conditions',[])}


class Crafting:
    def __init__(self,native,workspace):
        self.native=native;self.root=Path(workspace);self.units=[];self.unavailable=[];self.strings={};self.nodes={}

    def unit(self,path,value,semantic=None,file=CATALOG):
        self.units.append({'file':file,'path':path,'value':value,'semantic':value if semantic is None else semantic})

    def missing(self,target,error):self.unavailable.append({'catalog':CATALOG,'target':target,'reason':str(error)})

    def document(self,path):
        if path not in self.nodes:
            # Some saved project exports contain a broken byte in an unrelated
            # localized literal. Isolate it; semantic() rejects any affected rule.
            text=self.native.file(path).read_bytes().decode('utf-8-sig',errors='replace')
            self.nodes[path]=tree.parse(text)
            if '\ufffd' in text:self.missing(path,'Invalid UTF-8 isolated; affected native rules remain unavailable')
        return self.nodes[path]

    def text(self,value,language='zh'):
        match=re.search(r'\bguid\s*=\s*#([A-Fa-f0-9]{32})',value or '')
        if not match:raise ValueError('Native localization reference unavailable')
        if language not in self.strings:
            filename='hunter/localization/packages/'+{'zh':'simplifiedchinese','en':'english'}[language]+'/menus.locpack'
            with self.native.file(filename).open(encoding='utf-8-sig',newline='') as stream:self.strings[language]={r[0].upper():r[2].replace('\r\n','\n') for r in csv.reader(stream) if len(r)>2}
        return self.strings[language][match[1].upper()]

    def scan(self):
        records={};blueprints=[];blueprint_uids=set();owners={}
        unreleased=json.loads((self.root/'data/equipment/native-map.json').read_text('utf8')).get('unreleased_items',{})
        for ns in ('hunter','rogue'):
            directory=self.native.file(ns+'/game system data/juice/item')
            found=subprocess.run(['rg','-l','^CraftingBlueprintItem |^ArmorItem |^WeaponItem ',str(directory),'-g','*.mitem'],capture_output=True,text=True,encoding='utf8')
            if found.returncode not in (0,1):raise ValueError('Native item scan failed: '+found.stderr)
            for file in sorted(map(Path,found.stdout.splitlines())):
                source=file.relative_to(self.native.root).as_posix()
                try:
                    doc=self.native.document(source)
                    for row in doc['resources']:
                        uid=row['resource_uid']
                        if row['resource_type'] in ('ArmorItem','WeaponItem'):
                            if uid in unreleased:continue
                            if uid in records:raise RuntimeError('Duplicate native item UID: '+uid)
                            records[uid]=row
                        elif row['resource_type']=='CraftingBlueprintItem':
                            if uid in blueprint_uids:raise RuntimeError('Duplicate native blueprint UID: '+uid)
                            blueprint_uids.add(uid);blueprints.append(row)
                except (OSError,ValueError) as error:self.missing(source,error)
            for file in sorted(directory.glob('*.mgearset')):
                source=file.relative_to(self.native.root).as_posix()
                for row in self.native.document(source)['resources']:
                    if row['resource_type']!='GearSet':continue
                    for link in links(self.native,row,'myItems'):owners.setdefault(link['target_uid'],set()).add('set:'+row['resource_uid'].lower())
        return records,blueprints,owners

    def source_infos(self):
        infos={}
        for node in tree.walk(self.document(CRAFT)):
            if not node['header'].startswith('SourceInfo '):continue
            try:
                raw=tree.prop(node,'mySourceText');guid=re.search(r'guid\s*=\s*#([A-Fa-f0-9]{32})',raw)[1].lower()
                row={'tags':tree.tags(node,'myItemTags'),'introduction_level':int(tree.prop(node,'myIntroductionLevel','0')),'source':CRAFT}
                infos['blueprint_source_'+guid]=row
                for key,value in row.items():self.unit(['sources','blueprint_source_'+guid,key],value)
                # A missing translation must not erase otherwise valid links.
                row['text']=self.text(raw);self.unit(['sources','blueprint_source_'+guid,'text'],row['text'])
            except (ValueError,KeyError,TypeError) as error:self.missing('SourceInfo '+node['header'],error)
        return infos

    def identities(self,db,records,owners,projection):
        known={};entities={e['id']:e for e in projection['entities']}
        for identity,entity in db['entities'].items():
            rows=[]
            if entity['template']=='武器信息':
                saved=entity.get('collections',{}).get('武器型号资料',{}).get('rows',[])
                weapons={r['data']['装备UID']:r['data'] for r in saved}
                for unit in entities.get(identity,{}).get('units',[]):
                    if unit['target']['field']=='data':
                        model=unit['semantic'];uid=model['装备UID']
                        weapons[uid]={**weapons.get(uid,{}),**model}
                for weapon in weapons.values():
                    for binding in [{'uid':weapon['装备UID']},*weapon.get('variants',[])]:
                        uid=binding['uid'];native=records.get(uid)
                        if native is None:self.missing('item:'+uid,'Weapon item unavailable');continue
                        data={'entity_id':identity,'collection':'武器型号资料','record_id':weapon['stable_id'],
                              'slot':weapon['group'],'kind':weapon['kind'] if weapon['kind'] in ('named','exotic') else 'weapon',
                              'source':native['_source'],'tags':item_tags(self.native,native),'quality':scalar(self.native,native,'myQuality','Grey'),
                              'name':weapon['装备名称']}
                        for key,value in data.items():self.unit(['items',uid,key],value)
                        known[uid]=data
                continue
            if identity.startswith('exotic:'):rows.append((identity.split(':')[1].upper(),None,entity['fields']))
            for field,collection in entity.get('collections',{}).items():
                for row in collection['rows']:
                    uid=row.get('装备UID')
                    if not uid and re.fullmatch(r'gear_[a-f0-9]{32}',row.get('stable_id','')):
                        candidate=row['stable_id'][5:].upper()
                        if candidate in records and identity in owners.get(candidate,set()):
                            uid=candidate;target={'field':'装备UID','records':[{'field':field,'template':collection['template'],'id':{'stable_id':row['stable_id']}}]}
                            entities[identity]['units'].append({'target':target,'value':uid,'semantic':{'uid':uid,'owner':identity}})
                    if uid:rows.append((uid.upper(),field,row))
            for uid,field,row in rows:
                try:
                    native=records[uid]
                    if re.search(r'milestone|level\d+boost',native['internal_name'],re.I):continue
                    registered=owners.get(uid,set())&set(db['entities'])
                    if registered and registered!={identity}:raise ValueError('Native equipment ownership conflicts with registered page')
                    brand=links(self.native,native,'myGearBrand')
                    slot=row.get('装备部位') or (field or '').replace('型号资料','')
                    if slot not in SLOTS.values():slot=EQUIPMENT_SLOTS.get(scalar(self.native,native,'myEquipmentSlot'),slot)
                    data={'entity_id':identity,'collection':field,'record_id':row.get('stable_id') or uid,'slot':slot,'kind':'exotic' if identity.startswith('exotic:') else 'named' if row.get('stable_id') else 'gear_set' if entity['template']=='装备组信息' else 'brand','source':native['_source'],'tags':item_tags(self.native,native),'quality':scalar(self.native,native,'myQuality','Grey')}
                    if brand:data['brand_uid']=brand[0]['target_uid']
                    for key,value in data.items():self.unit(['items',uid,key],value)
                    known[uid]=data
                except (ValueError,KeyError,OSError) as error:self.missing('item:'+uid,error)
        return known

    def blueprint_targets(self,rows,known,records,owners,db):
        brands={}
        for item in known.values():
            if item.get('brand_uid'):brands.setdefault(item['brand_uid'],set()).add(item['entity_id'])
        for blueprint in rows:
            if 'template' in blueprint['internal_name'].lower():continue
            for link in links(self.native,blueprint,'myPossibleCraftedItems') or links(self.native,blueprint,'myCraftedItem'):
                uid=link['target_uid']
                if uid in known or uid not in records:continue
                native=records[uid]
                if re.search(r'milestone|level\d+boost',native['internal_name'],re.I):continue
                brand=links(self.native,native,'myGearBrand');matches=owners.get(uid,set())&set(db['entities'])
                if not matches and brand:matches=brands.get(brand[0]['target_uid'],set())
                if len(matches)!=1:continue
                identity=next(iter(matches));entity=db['entities'][identity]
                if scalar(self.native,native,'myIsNamed','FALSE')=='TRUE':continue
                slot=EQUIPMENT_SLOTS.get(scalar(self.native,native,'myEquipmentSlot'))
                if not slot:continue
                data={'entity_id':identity,'collection':None,'record_id':uid,'slot':slot,'kind':'gear_set' if entity['template']=='装备组信息' else 'brand',
                      'source':native['_source'],'tags':item_tags(self.native,native),'quality':scalar(self.native,native,'myQuality','Grey'),'name':self.native.text(native,'myUIName')}
                if brand:data['brand_uid']=brand[0]['target_uid']
                for key,value in data.items():self.unit(['items',uid,key],value)
                known[uid]=data

    def blueprints(self,rows,known,infos):
        result={}
        for native in rows:
            uid=native['resource_uid']
            try:
                if 'template' in native['internal_name'].lower():continue
                random=links(self.native,native,'myPossibleCraftedItems')
                targets=random or links(self.native,native,'myCraftedItem')
                if not any(t['target_uid'] in known for t in targets):continue
                if any(t['target_uid'] not in known for t in targets):raise ValueError('Unmapped blueprint target; preserve existing relation')
                tags=item_tags(self.native,native)
                if not tags:raise ValueError('Blueprint has explicit empty tags; availability unresolved')
                if uid in result:raise ValueError('Duplicate blueprint UID')
                own_name=[f for f in native['fields'] if f['field']=='myUIName' and f.get('guid') and len(f['context'])==1]
                name=self.native.text(native,'myUIName') if own_name else None
                category=scalar(self.native,native,'myBlueprintCategory')
                upgrade=scalar(self.native,native,'myBlueprintSubCategory')=='Upgrade'
                conversion=category=='Weapon' and any(tag.startswith('Crafting_Exotic_Convert_') for tag in tags)
                data={'targets':[t['target_uid'] for t in targets],'random':bool(random),'source':native['_source'],'tags':tags,
                      'purpose':'conversion' if conversion else 'reconfigure' if upgrade else 'craft',
                      'kind':'retaliation' if 'Crafting_Exotic_Outcasts' in tags else None,
                      'name':name,'category':category,'source_refs':sorted(i for i,r in infos.items() if set(r['tags'])&set(tags)),
                      'obtainable':scalar(self.native,native,'myIsObtainable','TRUE')=='TRUE',
                      'quality_override':scalar(self.native,native,'myCraftedItemQualityOverride','Grey') if scalar(self.native,native,'myShouldUseCraftingQualityOverride','FALSE')=='TRUE' else None,
                      'max_level':scalar(self.native,native,'myCraftedItemMaxLevel','30'),'max_tier':scalar(self.native,native,'myCraftedItemMaxTier','-1'),'conditions':[]}
                for field in ('myConditions','myAlreadyCraftedConditions'):
                    member=self.native.member(native,field)
                    if member:
                        node=next(n for n in tree.walk(self.document(member['_source'])) if member['resource_uid'] in n['header'])
                        condition=tree.child(node,field)
                        if condition and (member['resource_uid']==uid or any(n['properties'] for n in [condition,*tree.walk(condition)])):
                            data['conditions'].append({'field':field,**tree.semantic(condition)})
                if conversion:
                    requirements=[n for n in tree.walk(self.document(CRAFT)) if n['header'].startswith('CraftingItemRequirementDefinition ')
                                  and tree.prop(n,'myTag') in tags]
                    required=[tree.prop(n,'myItemTag') for rule in requirements for n in tree.walk(rule)
                              if n['header'].startswith('CraftingItemRequirement ')]
                    inputs=sorted(i for i,item in known.items() if set(required)&set(item['tags']))
                    if len(required)!=1 or len(inputs)!=1:raise ValueError('Unresolved appearance conversion ingredient')
                    data['input_uid']=inputs[0]
                for key,value in data.items():self.unit(['blueprints',uid,key],value)
                result[uid]=data
            except (ValueError,KeyError,OSError) as error:self.missing('blueprint:'+uid,error)
        return result

    def material_conversions(self,rows):
        conversions={}
        for blueprint in rows:
            tags=item_tags(self.native,blueprint)
            if not any(tag.startswith('Crafting_Optimization_Material_Conversion_') for tag in tags):continue
            uid=blueprint['resource_uid']
            try:
                target,=links(self.native,blueprint,'myCraftedItem')
                paths=[p for p in self.native.includes(blueprint['_source']) if Path(p).stem.casefold()==target['target_name'].casefold()]
                path,=paths
                item=self.native.record(path,target['target_uid'])
                if item['resource_type']!='ResourceItem':raise ValueError('Unexpected currency conversion result')
                currency,=links(self.native,item,'myCurrencyResource')
                value={'name':self.native.text(item,'myUIName'),'source':blueprint['_source'],'target_uid':target['target_uid'],
                       'result_source':path,'currency_uid':currency['target_uid'],'amount':int(scalar(self.native,item,'myResourceValue')),
                       'quality':scalar(self.native,item,'myQuality'),'tags':tags}
                conversions[uid]=value
                for field,data in value.items():self.unit(['material_conversions',uid,field],data)
            except (ValueError,KeyError,TypeError,OSError) as error:self.missing('material_conversion:'+uid,error)
        return conversions

    def economics(self,blueprints,known):
        used=set(t for b in blueprints.values() for t in b['tags'])|set(t for i in known.values() for t in i['tags'])
        rules={};deconstruction={};currencies=set()
        for source,types in ((CRAFT,('CraftingCurrencyDefinition','CraftingItemRequirementDefinition')),(DECON,('DeconstructionDefinition',))):
            for node in tree.walk(self.document(source)):
                kind=node['header'].split()[0]
                if kind not in types:continue
                tag=tree.prop(node,'myTag')
                if tag not in used:continue
                try:
                    if kind=='CraftingItemRequirementDefinition':
                        self.unit(['item_requirements',tag],tree.semantic(node));continue
                    qualities={}
                    for q in node['children'][0]['children']:
                        quality=tree.prop(q,'myQuality','Grey');outputs=[]
                        if kind=='CraftingCurrencyDefinition':
                            price=tree.child(q,'myPrice')
                            if price:outputs.append({**currency_requirement(price),'kind':'price'})
                            requirements=tree.child(q,'myCurrencyRequirements')
                            if requirements:
                                outputs.extend({**currency_requirement(r),'kind':'material'} for r in requirements['children'])
                        else:
                            for r in tree.walk(q):
                                if not r['header'].startswith('DeconstructionCurrency '):continue
                                outputs.append({**currency_requirement(r),'chance_percent':float(tree.prop(r,'myChance','100')),
                                                'perk':tree.prop(r,'myActivatedWithPerk','FALSE')=='TRUE','extra_quantity':tree.prop(r,'myUseExtraQuantityBonus','FALSE')=='TRUE'})
                        qualities[quality]=outputs;currencies.update(r['currency_uid'] for r in outputs)
                    group='crafting_rules' if kind=='CraftingCurrencyDefinition' else 'deconstruction_rules'
                    self.unit([group,tag],{'source':source,'qualities':qualities})
                    (rules if kind=='CraftingCurrencyDefinition' else deconstruction)[tag]=qualities
                except (ValueError,KeyError,IndexError) as error:self.missing(kind+':'+str(tag),error)
        return currencies,deconstruction

    def materials(self,currencies,deconstruction,known,db):
        sets=json.loads((self.root/'data/gear-sets/sets.json').read_text('utf8'))
        ui=json.loads((self.root/'data/brand-sets/equipment-ui.json').read_text('utf8'))
        base=json.loads((self.root/'data/brand-sets/equipment-base-rules.json').read_text('utf8'))
        gear=json.loads((self.root/'data/gear-sets/dismantle-rules.json').read_text('utf8'))
        identities={r['id']:r['currency_uid'] for group in [gear['common']['fixed_materials'],gear['common']['chance_materials'],*gear['slots'].values()] for r in group}
        currencies.update(row['material']['currency_uid'] for row in sets['sets'] if row.get('material'))
        currencies.update(row['native']['currency_uid'] for row in ui['material_display'].values() if row.get('native',{}).get('currency_uid'))
        nodes={re.search(r'uid=([A-Fa-f0-9]{32})',n['header'])[1].upper():n for n in tree.walk(self.document(CURRENCIES)) if re.search(r'uid=([A-Fa-f0-9]{32})',n['header'])}
        names={}
        for uid in sorted(currencies):
            try:
                node=nodes[uid];raw=tree.prop(node,'myUIName');name=self.text(raw);names[uid]=name
                self.unit(['currencies',uid,'name'],name)
                self.unit(['currencies',uid,'source'],CURRENCIES)
                quality=tree.prop(node,'myQuality')
                if quality is not None:self.unit(['currencies',uid,'quality'],quality)
            except (ValueError,KeyError,TypeError) as error:self.missing('currency:'+uid,error)
        # The existing public catalogs remain the Reader's display authority.
        # Currency IDs are joined once here; icons/observed quality are untouched.
        def update_group(file,at,rows,quality,tags):
            for row in rows:
                uid=row.get('currency_uid') or identities.get(row.get('id'))
                key={'key':'id','value':row['id']} if row.get('id') else {'key':'currency_uid','value':uid}
                if not uid:continue
                target=at+[key]
                found=[r for tag in tags for r in deconstruction.get(tag,{}).get(quality,[]) if r['currency_uid']==uid]
                if len(found)!=1:continue
                native=found[0]
                try:
                    if ('chance_percent' in row)!=(native['chance_percent']<100) or bool(row.get('requires_perk_level'))!=native['perk']:
                        raise ValueError('Dismantle probability or perk classification changed; retain existing display rule')
                    value=bracket_amount(native['brackets'])
                    if 'base_amount' in row:self.unit(target+['base_amount'],value,file=file)
                    if 'use_extra_quantity_bonus' in row:self.unit(target+['use_extra_quantity_bonus'],native['extra_quantity'],file=file)
                    if 'chance_percent' in row:self.unit(target+['chance_percent'],native['chance_percent'],file=file)
                    # Extra-quantity behavior differs between Orange and GearSet.
                    # Preserve measured final yields while that runtime rule is open.
                    if not native['extra_quantity']:
                        self.unit(target+['amount'],{'min':value,'max':value},file=file)
                    else:self.missing('dismantle:'+quality+':'+uid,'Extra-quantity final yield retained from existing gameplay catalog')
                except ValueError as error:self.missing('dismantle:'+uid,error)
        for slot,row in base['部位'].items():
            for group in ('fixed_materials','chance_materials'):
                update_group('data/brand-sets/equipment-base-rules.json',['部位',slot,'dismantle',group],row['dismantle'][group],'Orange',['Economy_Gear','Economy_'+dict((v,k) for k,v in SLOTS.items())[slot]])
        for group in ('fixed_materials','chance_materials'):
            update_group('data/gear-sets/dismantle-rules.json',['common',group],gear['common'][group],'GearSet',['Economy_Gear','Economy_GearSet'])
        for slot,rows in gear['slots'].items():
            update_group('data/gear-sets/dismantle-rules.json',['slots',slot],rows,'GearSet',['Economy_'+dict((v,k) for k,v in SLOTS.items())[slot]])
        # Dedicated materials are derived from item economy tags, not name guesses.
        for identity,entity in db['entities'].items():
            if entity['template'] in ('奇特装备信息','武器信息'):continue
            items=[i for i in known.values() if i['entity_id']==identity]
            found=set()
            for item in items:
                for tag in item['tags']:
                    if tag in {'Economy_Gear','Economy_GearSet',*('Economy_'+s for s in SLOTS)}:continue
                    found.update(r['currency_uid'] for r in deconstruction.get(tag,{}).get(item['quality'],[]))
            if len(found)==1:
                uid=next(iter(found));self.unit(['materials',identity,'currency_uid'],uid)
                definitions=[r for item in items for tag in item['tags'] for r in deconstruction.get(tag,{}).get(item['quality'],[]) if r['currency_uid']==uid]
                try:
                    values={bracket_amount(r['brackets']) for r in definitions}
                    if len(values)!=1 or any(r['extra_quantity'] or r['perk'] or r['chance_percent']!=100 for r in definitions):raise ValueError('Dedicated material final yield requires review')
                    value=next(iter(values));self.unit(['materials',identity,'amount'],{'min':value,'max':value})
                    if entity['template']=='装备组信息':
                        self.unit(['sets',{'key':'id','value':identity},'dismantle','brand_material_amount'],{'min':value,'max':value},file='data/gear-sets/sets.json')
                except ValueError as error:self.missing('dismantle:'+identity,error)

    def project(self,db,projection):
        records,rows,owners=self.scan();infos=self.source_infos();known=self.identities(db,records,owners,projection)
        self.blueprint_targets(rows,known,records,owners,db)
        blueprints=self.blueprints(rows,known,infos)
        conversions=self.material_conversions(rows)
        currencies,deconstruction=self.economics({**blueprints,**conversions},known)
        currencies.update(r['currency_uid'] for r in conversions.values())
        self.materials(currencies,deconstruction,known,db)
        from .native_sources import project as sources
        sources(self,known,blueprints,rows)
        from .native_source_rules import project as source_rules
        source_rules(self,known,blueprints,records)
        from .native_attributes import project as attributes
        attributes(self)
        return {'catalogs':self.units,'unavailable':self.unavailable,'items':known,'blueprints':blueprints,'deconstruction':deconstruction,'currencies':currencies}
