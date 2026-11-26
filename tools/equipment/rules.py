"""Project item configurations through their native UID links and inheritance."""
import json
from pathlib import Path
from tools.brand_sets.native_structure import StructureReader, contexts, minor_count, mod_count

COLORS={'43A2C97052209A23000004CDD0FB54EC':'red','5D4179F15AC362CC0001190A8D09DA48':'blue','5D4179F15BF80F4E00032B980881308F':'yellow'}
SLOTS={'Face':'mask','Back':'backpack','Chest':'chest','Hands':'gloves','Thighs':'holster','Knees':'kneepads'}

class EquipmentRules:
    def __init__(self,native):
        self.native=native;self.reader=StructureReader(native.root);self.configs={};self.pools={}

    def index(self):
        if self.configs:return
        for path in sorted(self.native.root.glob('hunter/game system data/juice/itemgeneration/configs/*code1_data23.mitemgenerationconfigs')):
            document=self.reader.read(path)
            for link in document['links']:
                if link['field']=='myItemGenerationConfigLink':self.configs.setdefault(link['target_uid'],[]).append((path,document['resources'][link['source_index']]['internal_name']))
        for path in sorted(self.native.root.glob('hunter/game system data/juice/itemgeneration/attributelists/*code1_data23.mitemgenerationattributelists')):
            for row in self.reader.read(path)['resources']:
                if row['resource_type']=='AttributeListContainer':self.pools[row['resource_uid']]=(path,row['internal_name'])

    def core(self,quality):
        def extract(record,links):
            groups=[c for c in contexts(record,links,'QualityAttributeSlots') if any(p['field']=='myQuality' and p['raw_value']==quality and p['context']==c for p in record['properties'])]
            if not groups:return None
            if len(groups)!=1:raise ValueError('Ambiguous core quality')
            cores=[]
            for slot in contexts(record,links,'ItemAttributeSlot'):
                if slot[:len(groups[0])]!=groups[0]:continue
                props={p['field']:p['raw_value'] for p in record['properties'] if p['context']==slot}
                if props.get('myIsCoreAttribute')!='TRUE':continue
                preset=props.get('myPresetAttribute','0'*32)
                if preset!='0'*32:cores.append(('fixed',[COLORS[preset]]));continue
                refs={l['target_uid'] for l in links if l['field']=='AttributeListContainer' and l['context'][:len(slot)]==slot}
                if not refs:raise ValueError('Random core pool unavailable')
                types=set()
                for uid in refs:
                    path,name=self.pools[uid]
                    def attributes(row,_links):
                        values=[p['raw_value'] for p in row['properties'] if p['field']=='myAttribute']
                        return values or None
                    values,_=self.reader.resolve(path,name,attributes)
                    types.update(COLORS[value] for value in values)
                cores.append(('random',[c for c in ['red','blue','yellow'] if c in types]))
            if not cores:raise ValueError('Core slots unavailable')
            selections={c[0] for c in cores}
            if len(selections)!=1 or 'random' in selections and len({tuple(c[1]) for c in cores})!=1:raise ValueError('Mixed core configuration requires explicit slots')
            types=[c for c in ['red','blue','yellow'] if any(c in r[1] for r in cores)]
            if selections=={'fixed'} and len(types)!=len(cores):raise ValueError('Duplicate fixed core')
            return {'count':len(cores),'selection':cores[0][0],'types':types}
        return extract

    def item(self,binding):
        self.index();path=self.native.file(binding['source']);document=self.reader.read(path)
        found=[(i,r) for i,r in enumerate(document['resources']) if (r['resource_uid'] or '').lower()==binding['uid'].lower() and r['resource_type']=='ArmorItem']
        if len(found)!=1:raise ValueError('Armor identity missing')
        index,record=found[0]
        def scalar(key):
            def read(row,_links):
                values=[p['raw_value'] for p in row['properties'] if p['field']==key and len(p['context'])==1]
                if len(values)>1:raise ValueError('Ambiguous item '+key)
                return values[0] if values else None
            return self.reader.resolve(path,record['internal_name'],read)[0]
        slot=SLOTS[scalar('myEquipmentSlot')];quality=scalar('myQuality')
        links=[l['target_uid'] for l in document['links'] if l['source_index']==index and l['field']=='myItemGenerationConfig']
        configs=self.configs.get(links[0],[]) if len(links)==1 else []
        def configured(counter):
            if len(configs)!=1:raise ValueError('Generation config missing or ambiguous')
            config,name=configs[0]
            return self.reader.resolve(config,name,counter)[0]
        def minors(row,refs):return minor_count(row,refs,quality,self.reader.categories(configs[0][0]))
        def mods(row,refs):return mod_count(row,refs,quality)
        values={};failures={}
        for field,read in [('core',lambda:configured(self.core(quality))),('minor_count',lambda:configured(minors)),('mods',lambda:self.reader.resolve(path,record['internal_name'],mods)[0])]:
            try:values[field]=read()
            except (OSError,ValueError,KeyError,IndexError) as error:values[field]=None;failures[field]=str(error)
        return slot,values,failures

    def project(self,entity):
        groups={};unavailable=[];blocked=set()
        for binding in entity['bindings']:
            if not binding['source'].endswith('.mitem') or 'myUIName' not in [v.get('property') for v in binding['fields'].values()]:continue
            steps=binding.get('records',[]);named=steps and steps[0]['field']=='具名装备资料'
            try:
                slot,values,failures=self.item(binding)
                identity='named:'+steps[0]['id']['stable_id'] if named else 'slot:'+slot
                groups.setdefault(identity,[]).append(values)
                for field,reason in failures.items():
                    if entity['template']!='奇特装备信息' or field=='mods':unavailable.append({'entity':entity['id'],'target':{'field':field,'id':identity,'uid':binding['uid']},'reason':reason})
            except (OSError,ValueError,KeyError,IndexError) as error:
                identity='named:'+steps[0]['id']['stable_id'] if named else 'slot:'+steps[0]['field'].removesuffix('型号资料') if steps and steps[0]['field'].endswith('型号资料') else '*'
                blocked.add(identity)
                unavailable.append({'entity':entity['id'],'target':{'field':'属性配置','uid':binding['uid']},'reason':str(error)})
        units=[]
        for identity,rows in groups.items():
            if '*' in blocked or identity in blocked:continue
            for field,value in rows[0].items():
                if any(row[field] is None for row in rows):continue
                if any(row[field]!=value for row in rows):
                    unavailable.append({'entity':entity['id'],'target':{'field':field,'id':identity},'reason':'Models disagree; retain existing rules'});continue
                if entity['template']=='奇特装备信息':
                    if field!='mods':continue
                    target={'field':'插件槽数'};value=str(value)
                else:target={'field':field,'records':[{'field':'属性配置','id':{'id':identity}}]}
                units.append({'target':target,'value':json.dumps(value,ensure_ascii=False,separators=(',',':')) if not isinstance(value,str) else value,'semantic':value})
        return units,unavailable
