"""Project only evidenced native fields; unavailable inputs never emit deletions."""
import csv
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
import json
from pathlib import Path
import re
import hashlib
from tools.asset_import.text_evidence import native_definitions

ROOT = Path(__file__).resolve().parents[2]
TONES = {**dict(orange='orange', legendary_orange='gold', red='red', yellow='gold', light_blue='light_blue', white='white', blue='blue'), 'legendary orange':'gold'}

def bindings(entity):
    for group in entity['bindings']:
        source={key:group[key] for key in ('source','uid','follow') if key in group}
        for field,binding in group['fields'].items():
            yield {**binding,**source,'target':{'field':field,'records':group['records']}}

def richtext(text):
    text=re.sub(r'<br\s*/?>','\n',text,flags=re.I)
    # Some shipped menu lines omit the closing quote in the opening color tag.
    text=re.sub(r'<color name="([a-z_ ]+)>', r'<color name="\1">', text)
    stack=[]
    def replace(m):
        if m[1]:
            if m[1].strip() not in TONES:raise ValueError('Unknown native color')
            stack.append(m[1])
            return '{{TD2文字|色='+TONES[m[1].strip()]+'|文='
        if m[2]:
            name=re.fullmatch(r'hunter/baked/ui/loose_images/ui_player_(offense|defense|utility)\.dds',m[2])
            if not name: raise ValueError('Unknown native inline image')
            return '{{TD2图标|类别=state|键='+dict(offense='red',defense='blue',utility='yellow')[name[1]]+'}}'
        return '}}' if stack and stack.pop() else ''
    result=re.sub(r'<color name=["“”]([^"“”]+)["“”]>|<img src="([^"]+)"\s*/?>|</color>',replace,text)
    if '<' in result or '>' in result: raise ValueError('Unknown native markup')
    return result+'}}'*len(stack)

def number(raw,multiplier=1):
    value=format(Decimal(raw)*Decimal(multiplier),'f')
    return value.rstrip('0').rstrip('.') if '.' in value else value

def parameter(value):
    if value['type'] not in ('Percentage','FlatValue'):raise ValueError('Unknown native parameter type')
    result=Decimal(value['raw'])*(100 if value['type']=='Percentage' else 1)
    rounding=value.get('round')
    if rounding not in (None,'None'):
        steps={'Ceiling':(1,ROUND_CEILING),'Floor':(1,ROUND_FLOOR),'Nearest':(1,ROUND_HALF_UP),'NearestTenth':('0.1',ROUND_HALF_UP),'NearestHalf':('0.5',ROUND_HALF_UP)}
        if rounding not in steps:raise ValueError('Unknown native rounding mode')
        step,method=steps[rounding];step=Decimal(step);result=(result/step).quantize(Decimal(1),rounding=method)*step
    return number(str(result))

class Native:
    def __init__(self,root):
        self.root=Path(root).resolve();self.cache={};self.texts={};self.attributes={}

    def file(self,path):
        target=(self.root/path).resolve()
        if not target.is_relative_to(self.root): raise ValueError('Native path outside resource root')
        return target

    def document(self,path):
        if path not in self.cache:
            data=native_definitions(self.file(path).read_bytes(),include_data=True,include_objects=True)
            if data['issues']: raise ValueError('Native parse issues: '+path)
            for record in data['resources']:record['_source']=path
            self.cache[path]=data
        return self.cache[path]

    def record(self,path,uid):
        rows=[r for r in self.document(path)['resources'] if (r['resource_uid'] or '').lower()==uid.lower()]
        if len(rows)!=1: raise ValueError('Native identity missing or ambiguous: '+uid)
        return rows[0]

    def bound_record(self,binding):
        follow=binding.get('follow')
        if not follow:return self.record(binding['source'],binding['uid'])
        links=[]
        for reference in follow:
            matches=[l for l in self.document(reference['source'])['links'] if l['reference_uid']==reference['reference_uid']]
            if len(matches)!=1:raise ValueError('Native relation missing or ambiguous')
            links.extend(matches)
        if len({l['target_uid'] for l in links})!=1:raise ValueError('Native relation differs between configurations')
        link=links[0]
        paths=[binding['source']]+[ns+'/game system data/juice/talent/'+link['target_name']+'.mtalent' for ns in ['hunter','rogue']]
        for path in dict.fromkeys(paths):
            try:return self.record(path,link['target_uid'])
            except (OSError,ValueError):pass
        raise ValueError('Native relation target unavailable: '+link['target_uid'])

    def includes(self, source):
        return [(i['path'] if i['path'].startswith(('hunter/','rogue/')) else
                 (Path(source).parent/i['path']).as_posix()) for i in self.document(source)['includes']]

    def definition(self, source, name=None, uid=None, seen=None, types=None):
        """Resolve only within the declared include graph, never by a similar filename."""
        seen=set() if seen is None else seen
        queue=[source]
        while queue:
            path=queue.pop(0)
            if path in seen:continue
            seen.add(path)
            doc=self.document(path)
            found=[r for r in doc['resources'] if (not types or r['resource_type'] in types) and (uid and r['resource_uid']==uid or
                   not uid and (r['internal_name'] or '').casefold()==name.casefold())]
            if len(found)>1:raise ValueError('Ambiguous native definition: '+str(name or uid))
            if found:return found[0]
            includes=[p for p in self.includes(path) if not p.endswith('.fruit') and
                      not p.endswith('/itemincludes.juice')]
            includes.sort(key=lambda p:0 if name and Path(p).stem.casefold()==name.casefold() else 1)
            queue.extend(includes)
        return None

    def lineage(self,record):
        """Read the declared parent chain; callers stop at the first explicit member."""
        seen=set()
        while True:
            identity=(record.get('_source'),record['internal_name'])
            if identity in seen:raise ValueError('Native inheritance cycle')
            seen.add(identity);yield record
            parent=record.get('inheritance_name')
            if not parent:return
            source=record['_source'];document=self.document(source)
            matches=[r for r in document['resources'] if r['internal_name']==parent]
            if not matches and record['resource_type']=='WeaponItem':
                inherited=self.definition(source,name=parent)
                if inherited:matches=[inherited]
            if not matches:
                paths=[path for path in self.includes(source) if Path(path).stem.lower()==parent.lower()]
                if len(set(paths))!=1:raise ValueError('Native parent missing or ambiguous: '+parent)
                matches=[r for r in self.document(paths[0])['resources'] if r['internal_name']==parent]
            if len(matches)!=1:raise ValueError('Native parent missing or ambiguous: '+parent)
            record=matches[0]

    def member(self,record,field):
        """Resolve one root member, including explicit empty collections, child first."""
        for row in self.lineage(record):
            entries=row['properties']+row['fields']+row.get('empty_blocks',[])
            if any((len(p['context'])==1 and p['field']==field) or (len(p['context'])>1 and p['context'][1]['resource_type']==field) for p in entries):return row
        return None

    def override(self,record):
        """Select the PvP override by enum; its native default is the first member, PvP."""
        row=self.member(record,'myTalentOverrides')
        if row is None:return None
        contexts=[]
        for p in row['properties']+row['fields']+row.get('empty_blocks',[]):
            ctx=p['context']
            if len(ctx)>2 and ctx[1]['resource_type']=='myTalentOverrides' and ctx[2]['resource_type']=='TalentOverride' and ctx[:3] not in contexts:contexts.append(ctx[:3])
        matches=[]
        for ctx in contexts:
            kinds=[p['raw_value'] for p in row['properties'] if p['field']=='myOverrideType' and p['context']==ctx]
            if len(kinds)>1:raise ValueError('Ambiguous talent override type')
            kind=kinds[0] if kinds else 'PvP'
            if kind not in ('PvP','SHDWatch_DZPvP','Augments_DZBlackoutHardcore'):raise ValueError('Unknown talent override type')
            if kind=='PvP':matches.append((row,ctx))
        if len(matches)>1:raise ValueError('Ambiguous PvP override')
        return matches[0] if matches else None

    def enabled(self,override,field):
        """An omitted native override switch is FALSE; malformed switches are unavailable."""
        if override is None:return False
        row,ctx=override
        values=[p['raw_value'] for p in row['properties'] if p['field']==field and p['context']==ctx]
        if len(values)>1 or values and values[0] not in ('TRUE','FALSE'):raise ValueError('Invalid talent override switch: '+field)
        return values==['TRUE']

    def localization(self,language='zh'):
        if language not in self.texts:
            path='hunter/localization/packages/'+{'zh':'simplifiedchinese','en':'english'}[language]+'/menus.locpack'
            with self.file(path).open(encoding='utf-8-sig',newline='') as stream:
                self.texts[language]={r[0]:r[2].replace('\r\n','\n') for r in csv.reader(stream) if len(r)>2}
        return self.texts[language]

    def text(self,record,field,language='zh',mode=None):
        self.localization(language)
        if mode is None:
            owner=self.member(record,field)
            rows=[] if owner is None else [f for f in owner['fields'] if f['field']==field and len(f['context'])==1]
        else:
            override=self.override(record)
            rows=[] if override is None else [f for f in override[0]['fields'] if f['field']==field and f['context']==override[1]]
        if len(rows)!=1: raise ValueError('Native text binding missing: '+field)
        return self.texts[language][rows[0]['guid']]

    def attribute(self,uid):
        if not self.attributes:
            for namespace in ['hunter','rogue']:
                directory=self.file(namespace+'/game system data/juice/attribute/dictionary')
                for file in directory.glob('*.mdict'):
                    for row in self.document(file.relative_to(self.root).as_posix())['resources']:
                        self.attributes[row['resource_uid']]={p['field']:p['raw_value'] for p in row['properties'] if p['context'][-1].get('resource_uid')==row['resource_uid']}
        return self.attributes[uid]

    def talent(self,record,mode):
        if mode not in ('PvE','PvP'):raise ValueError('Unknown talent mode')
        override=self.override(record) if mode=='PvP' else None
        if self.enabled(override,'myUseOverrideBonusList'):
            owner,scope=override;scope=scope+[{'resource_type':'myOverrideBonusList','internal_name':None,'resource_uid':None}]
        else:
            owner=self.member(record,'myBonusList');scope=None
        props=owner['properties'] if owner is not None else []
        values=[]
        for p in props:
            if p['field']!='myAttributeUID':continue
            ctx=p['context']
            if scope is not None:
                if ctx[:len(scope)]!=scope:continue
            elif len(ctx)<2 or ctx[1]['resource_type']!='myBonusList':continue
            raw=[a['raw_value'] for a in props if a['field']=='myValue' and a['context']==p['context']]
            if len(raw)>1:raise ValueError('Ambiguous talent parameter')
            # BonusAttributeRef.myValue defaults to zero. Retain its position
            # even when omitted, because tooltip placeholders index the list.
            attribute=self.attribute(p['raw_value']);values.append({'uid':p['raw_value'],'raw':number(raw[0] if raw else '0'),'type':attribute.get('myBonusType'),'decimals':attribute.get('myUINumDecimals'),'round':attribute.get('myRoundMode')})
        template=self.text(record,'myOverrideToolTipText',mode='PvP') if self.enabled(override,'myUseOverrideToolTipText') else self.text(record,'myToolTipText')
        used=sorted({int(i) for i in re.findall(r'\{(\d+)\}',template)})
        semantic={'template':template,'parameters':{str(i):values[i] for i in used}}
        rendered=re.sub(r'\{(\d+)\}',lambda m:parameter(values[int(m[1])]),template)
        return semantic,richtext(rendered)

    def bonus(self,record,attribute,count,mode,slot=None):
        values=[]
        for prop in record['properties']:
            if prop['field']!='myValue':continue
            ctx=prop['context'];unlock=next((c for c in ctx if c['resource_type']=='GearSetUnlock'),None)
            if not unlock:continue
            prefix=ctx[:ctx.index(unlock)+1]
            required=[p['raw_value'] for p in record['properties'] if p['field']=='myRequiredNumberOfItems' and p['context']==prefix]
            if not required:
                match=re.search(r'(\d+)',unlock['internal_name'] or '');required=[match[1]] if match else []
            if required!=[str(count)]:continue
            ids=[p['raw_value'] for p in record['properties'] if p['field']=='myAttributeUID' and p['context']==ctx]
            pvp=any(c['resource_type']=='GearSetEffectOverride' for c in ctx)
            if slot:
                if ctx[-1].get('internal_name')!=slot.get('PvP' if pvp else 'PvE'):continue
            elif ids!=[attribute]:continue
            if len(ids)!=1:raise ValueError('Native bonus attribute ambiguous')
            values.append((pvp,prop['raw_value'],ids[0]))
        matching=[(v,uid) for pvp,v,uid in values if pvp==(mode=='PvP')]
        if not matching and mode=='PvP':
            overrides=[p for p in record['properties']+record.get('empty_blocks',[]) if any(c['resource_type']=='GearSetEffectOverride' for c in p['context']) and any(c['resource_type']=='GearSetUnlock' and re.search(r'\b'+str(count)+r'\b',c.get('internal_name') or '') for c in p['context'])]
            if overrides:raise ValueError('Native PvP override incomplete')
            matching=[(v,uid) for pvp,v,uid in values if not pvp]
        if len(matching)!=1:raise ValueError('Native bonus missing or ambiguous')
        value,attribute=matching[0]
        kind=self.attribute(attribute).get('myBonusType')
        return {'attribute':attribute,'raw':number(value),'type':kind},number(value,100 if kind=='Percentage' else 1)

    def project(self,mapping):
        from tools.equipment.rules import EquipmentRules
        rules=EquipmentRules(self)
        saved=json.loads((ROOT/'data/equipment/records.json').read_text('utf8'))['entities']
        icons={}
        for entity in mapping['entities']:
            for binding in entity['bindings']:
                if not any(v['kind']=='talent' for v in binding['fields'].values()):continue
                identity=binding['records'][0]['id']
                row=next((r for r in saved.get(entity['id'],{}).get('effects',[]) if all(r.get(k)==v for k,v in identity.items())),{})
                if row.get('图标'):icons.setdefault(binding['uid'].lower(),set()).add(row['图标'])
        output={'schema_version':1,'entities':[],'unavailable':[]}
        for entity in mapping['entities']:
            units=[]
            for binding in bindings(entity):
                try:
                    record=self.bound_record(binding)
                    if binding['kind']=='text':
                        try:
                            semantic=self.text(record,binding['property'],binding.get('language','zh'))
                        except KeyError:
                            if 'fallback_language' not in binding:raise
                            semantic=self.text(record,binding['property'],binding['fallback_language'])
                        if binding['property']=='myUIName':semantic=re.sub(r'</?color\b[^>]*>','',semantic)
                        value=richtext(semantic)
                    elif binding['kind']=='talent':
                        semantic,value=self.talent(record,binding['mode'])
                        keys=icons.get(record['resource_uid'].lower(),set())
                        if len(keys)==1:
                            icon=next(iter(keys));units.append(dict(target={**binding['target'],'field':'图标'},value=icon,semantic={'uid':record['resource_uid'].lower(),'key':icon}))
                        else:output['unavailable'].append(dict(entity=entity['id'],target={**binding['target'],'field':'图标'},reason='Talent icon mapping unavailable'))
                    elif binding['kind']=='bonus':
                        semantic,value=self.bonus(record,binding['attribute'],binding['count'],binding['mode'],binding.get('slot'))
                        labels=mapping.get('bonus_attributes',{}).get(semantic['attribute'])
                        if binding.get('slot'):
                            if labels is None:raise ValueError('Native bonus attribute is not mapped: '+semantic['attribute'])
                            for field,label in labels.items():
                                units.append(dict(target={**binding['target'],'field':field},value=label,semantic={'attribute':semantic['attribute'],'value':label}))
                    else:raise ValueError('Unknown binding kind')
                    units.append(dict(target=binding['target'],value=value,semantic=semantic))
                except (OSError,ValueError,KeyError,IndexError,ArithmeticError) as error:
                    output['unavailable'].append(dict(entity=entity['id'],target=binding['target'],reason=str(error)))
            if entity.get('attribute_slots'):
                try:
                    for row in self.slots(entity['attribute_slots'],mapping):
                        target=[dict(field='属性槽',id={'槽位ID':row['id']},template='奇特装备属性槽')]
                        for field,value in row['fields'].items():
                            semantic=row['relation'] if field in ('类型','选择方式','属性规则','候选池') else value
                            units.append(dict(target=dict(field=field,records=target),value=value,semantic=semantic))
                except (OSError,ValueError,KeyError) as error:
                    output['unavailable'].append(dict(entity=entity['id'],target={'field':'属性槽'},reason=str(error)))
            extra,missing=rules.project(entity);units.extend(extra);output['unavailable'].extend(missing)
            output['entities'].append(dict(id=entity['id'],source=entity.get('source') or __import__('tools.identity',fromlist=['page']).page(entity['id'])['source'],template=entity['template'],units=units))
        if mapping.get('weapons'):
            from .weapons_native import WeaponNative
            from .weapon_projection import WeaponProjection
            weapons=WeaponProjection(WeaponNative(self.root)).project(mapping['weapons'])
            output['entities'].extend(weapons['entities']);output['unavailable'].extend(weapons['unavailable'])
        return output

    def slots(self,binding,mapping):
        document=self.document(binding['source'])
        matches=[l for l in document['links'] if l['field']=='myItemGenerationConfigLink' and l['target_uid']==binding['config_link']]
        if len(matches)!=1:raise ValueError('Native config link missing or ambiguous')
        record=document['resources'][matches[0]['source_index']]
        rows={}
        for prop in record['properties']:
            context=prop['context']
            if not any(c['resource_type']=='QualityAttributeSlots' and c['internal_name']=='Exotic' for c in context):continue
            slot=next((c for c in context if c['resource_type']=='ItemAttributeSlot'),None)
            if slot and context[-1]==slot:rows.setdefault(slot['internal_name'],{})[prop['field']]=prop['raw_value']
        if not rows:raise ValueError('Native attribute slots unavailable')
        result=[]
        for name,props in rows.items():
            identity=binding.get('identities',{}).get(name,'native_'+hashlib.sha256(name.encode()).hexdigest()[:16])
            preset=props.get('myPresetAttribute','0'*32);core=props.get('myIsCoreAttribute')=='TRUE'
            if preset!='0'*32:
                rule=mapping['attribute_rules'][preset];pool='';selection='预设'
            else:
                refs=sorted({l['target_uid'] for l in document['links'] if l['source_index']==matches[0]['source_index'] and l['field']=='AttributeListContainer' and any(c['resource_type']=='ItemAttributeSlot' and c['internal_name']==name for c in l['context'])})
                pool=mapping['attribute_pools'][';'.join(refs)];rule='';selection='随机'
            relation=dict(类型='主属性' if core else '次属性',选择方式=selection,属性规则=rule,候选池=pool)
            fields={**relation}
            if 'myPresetPercentage' in props:fields['预设百分位']=number(props['myPresetPercentage'])
            result.append(dict(id=identity,name=name,fields=fields,relation=relation))
        return result

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--resources',type=Path,default=ROOT/'resources/game/current/raw_files');parser.add_argument('--mapping',type=Path,default=ROOT/'data/equipment/native-map.json');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();native=Native(args.resources);result=native.project(__import__('tools.identity',fromlist=['read_json']).read_json(args.mapping))
    from tools.equipment.crafting import Crafting
    extra=Crafting(native,ROOT).project(json.loads((ROOT/'data/equipment/records.json').read_text('utf8')),result)
    result['catalogs']=extra['catalogs'];result['unavailable'].extend(extra['unavailable'])
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f"{len(result['entities'])} entities; {sum(len(e['units']) for e in result['entities'])} semantic fields; {len(result['unavailable'])} unavailable fields preserved")

if __name__=='__main__':main()
