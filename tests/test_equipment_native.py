from current_identity import entity_id
from tools import identity as identity_catalog
import copy
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
from tools.equipment.native import Native, bindings

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/equipment-native'
TALENT='hunter/game system data/juice/talent/warlock_talent_exotic_backpack_mk2.mtalent'
UID='346395BC5EFF32B00003AB84932B6FB5'

class NativeImportTests(unittest.TestCase):
    def test_generation_version_is_read_from_native_table(self):
        from tools.equipment.native_tree import GENERATION_VERSIONS, item_generation_version
        self.assertEqual(item_generation_version(Native(FIXTURE)), 'code1_data23')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            file=root/GENERATION_VERSIONS
            file.parent.mkdir(parents=True)
            original=(FIXTURE/GENERATION_VERSIONS).read_text('utf8')
            file.write_text(original.replace('23','24'),encoding='utf8')
            self.assertEqual(item_generation_version(Native(root)), 'code1_data24')
            file.write_text(original.replace('23','29'),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Unreviewed'):
                item_generation_version(Native(root))

    def talent_record(self,name):
        n=Native(FIXTURE)
        return n,n.document('hunter/game system data/juice/talent/'+name+'.mtalent')['resources'][0]

    def test_real_steel_pvp_update_preserves_pve_and_obeys_independent_switches(self):
        n,r=self.talent_record('talent_exotic_chest_firm_intent')
        pve=n.talent(r,'PvE');pvp=n.talent(r,'PvP')
        self.assertEqual(pve[0]['parameters']['0']['raw'],'2')
        self.assertEqual(pvp[0]['parameters']['0']['raw'],'6')
        changed=copy.deepcopy(r)
        row,ctx=n.override(changed)
        value=next(p for p in row['properties'] if p['field']=='myValue' and p['context'][:len(ctx)]==ctx)
        value['raw_value']='7.0'
        self.assertEqual(n.talent(changed,'PvE'),pve)
        self.assertEqual(n.talent(changed,'PvP')[0]['parameters']['0']['raw'],'7')
        bonus_switch=next(p for p in row['properties'] if p['field']=='myUseOverrideBonusList')
        bonus_switch['raw_value']='FALSE'
        self.assertEqual(n.talent(changed,'PvP')[0]['parameters']['0']['raw'],'2')
        bonus_switch['raw_value']='TRUE'
        row['fields']=[p for p in row['fields'] if p['field']!='myOverrideToolTipText']
        with self.assertRaisesRegex(ValueError,'text binding missing'):n.talent(changed,'PvP')
        next(p for p in row['properties'] if p['field']=='myUseOverrideToolTipText')['raw_value']='FALSE'
        self.assertEqual(n.talent(changed,'PvP')[0]['parameters']['0']['raw'],'7')
        row['properties'].append(dict(field='myOverrideType',raw_value='SHDWatch_DZPvP',context=ctx))
        self.assertEqual(n.talent(changed,'PvP'),pve)

    def test_real_negotiator_pvp_tooltip_only_parameter_changes_its_mode(self):
        n,r=self.talent_record('talent_gearset_negotiatorsdilemma_6piece')
        pve=n.talent(r,'PvE');pvp=n.talent(r,'PvP')
        self.assertNotIn('5',pve[0]['parameters']);self.assertEqual(pvp[0]['parameters']['5']['raw'],'12')
        self.assertIn('12 米',pvp[1])
        changed=copy.deepcopy(r);row,ctx=n.override(changed)
        values=[p for p in row['properties'] if p['field']=='myValue' and p['context'][:len(ctx)]==ctx]
        values[5]['raw_value']='13.0'
        self.assertEqual(n.talent(changed,'PvE'),pve);self.assertIn('13 米',n.talent(changed,'PvP')[1])
        row['properties']=[p for p in row['properties'] if p['field']!='myUseOverrideToolTipText']
        self.assertNotIn('5',n.talent(changed,'PvP')[0]['parameters'])

    def test_real_perfect_talents_inherit_text_but_keep_child_parameters(self):
        for name in ['warlock_talent_deployed_skills_boost_allies_perfected','talent_backpack_status_effects_spread_perfect','talent_chest_headshots_blind_target_perfect','warlock_talent_armor_kits_overcharge_perfect']:
            with self.subTest(name=name):
                n,r=self.talent_record(name)
                for mode in ['PvE','PvP']:
                    semantic,text=n.talent(r,mode)
                    self.assertTrue(text);self.assertNotRegex(text,r'\{\d+\}')
                self.assertEqual(n.member(r,'myUIName'),r)
        n,r=self.talent_record('warlock_talent_deployed_skills_boost_allies_perfected')
        self.assertEqual([p['raw'] for p in n.talent(r,'PvE')[0]['parameters'].values()],['15','0.3','0.6'])
        self.assertEqual([p['raw'] for p in n.talent(r,'PvP')[0]['parameters'].values()],['4','0.3','0.6'])
        missing=copy.deepcopy(r);missing['inheritance_name']='missing_parent'
        with self.assertRaisesRegex(ValueError,'parent missing'):n.talent(missing,'PvE')
        cycle=copy.deepcopy(r);cycle['inheritance_name']=cycle['internal_name']
        with self.assertRaisesRegex(ValueError,'inheritance cycle'):n.talent(cycle,'PvE')

    def test_real_mode_updates_import_only_changed_description_and_initialize_without_overwrite(self):
        mapping=identity_catalog.read_json(ROOT/'data/equipment/native-map.json')
        cases=[]
        for title,name,index,new in [('钢铁意志','talent_exotic_chest_firm_intent',0,'7'),('谈判者困境','talent_gearset_negotiatorsdilemma_6piece',5,'13')]:
            n,r=self.talent_record(name)
            e=next(e for e in mapping['entities'] if e['id']==entity_id(title))
            targets={b['mode']:b['target'] for b in bindings(e) if b['kind']=='talent' and b['source'].endswith('/'+name+'.mtalent')}
            def project(record):
                units=[]
                for mode in ['PvE','PvP']:
                    semantic,value=n.talent(record,mode)
                    units.append(dict(target=targets[mode],semantic=semantic,value=value))
                return {k:e[k] for k in ['id','source','template']}|dict(units=units)
            before=project(r);changed=copy.deepcopy(r);owner,ctx=n.override(changed)
            [p for p in owner['properties'] if p['field']=='myValue' and p['context'][:len(ctx)]==ctx][index]['raw_value']=new
            cases.append(dict(before=before,after=project(changed)))
        script=r"""
const fs=require('fs'),assert=require('assert/strict'),{plan}=require('./tools/equipment/import.cjs'),database=require('./tools/equipment/database.cjs');
for(const {before,after} of JSON.parse(fs.readFileSync(0,'utf8'))){
 const read=source=>fs.readFileSync(source,'utf8'),input=e=>({schema_version:1,entities:[e]});
 const current=database.load(),first=plan(input(before),null,read,current);assert.deepEqual(first.database,current);
 const manual=structuredClone(current),pve=before.units[0].target,pvp=before.units[1].target;
 database.write(manual.entities[before.id],pve,'NON-GAME-FACT PvE 人工修订');database.write(manual.entities[before.id],pvp,'NON-GAME-FACT PvP 人工修订');
 assert.deepEqual(plan(input(before),first.baseline,read,manual).database,manual);
 const result=plan(input(after),first.baseline,read,manual);
 assert.equal(database.value(result.database.entities[before.id],pve),'NON-GAME-FACT PvE 人工修订');
 assert.equal(database.value(result.database.entities[before.id],pvp),after.units[1].value);
 assert.deepEqual(result.pages[0].fields,[pvp]);assert.equal(result.pages[0].raw,result.pages[0].before);
}
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps(cases),text=True,encoding='utf8',capture_output=True,cwd=ROOT)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_real_native_editor_reimport_and_reader_round_trip(self):
        mapping=identity_catalog.read_json(ROOT/'data/equipment/native-map.json')
        entity=next(e for e in mapping['entities'] if e['id']=='exotic:346395bc5eff309f0003a7d41bab9c36')
        mapping['entities']=[entity]
        mapping.pop('weapons',None)
        native=Native(FIXTURE)
        before=native.project(mapping)['entities'][0]
        record=native.record(TALENT,UID)
        parameters=[p for p in record['properties'] if p['field']=='myValue' and any(c['resource_type']=='TalentOverride' for c in p['context'])]
        parameters[8]['raw_value']=str(float(parameters[8]['raw_value'])+0.01)
        after=native.project(mapping)['entities'][0]
        script=r"""
const fs=require('fs'),assert=require('assert/strict'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const {plan}=require('./tools/equipment/import.cjs'),database=require('./tools/equipment/database.cjs'),effects=require('./ui/editor/src/page-effects.js'),local=require('./ui/editor/src/local-session.js'),catalog=require('./tools/equipment/catalog.cjs'),data=catalog.data();
const raw=fs.readFileSync(input.before.source,'utf8'),read=source=>source===input.before.source?raw:null;
const projection=entity=>({schema_version:1,entities:[entity]});
const first=plan(projection(input.before),null,read);assert.equal(first.pages[0].raw,raw);
const manual=structuredClone(first.database);
for(const row of manual.entities[input.before.id].effects)row.描述+='人工'+row.模式+'修订';
const unchanged=plan(projection(input.before),first.baseline,read,manual);assert.deepEqual(unchanged.database,manual);
const result=plan(projection(input.after),first.baseline,read,manual);
data.options.effectCatalog=database.references(result.database);
const editor=local.create(result.pages[0].raw,data.catalog,data.options),descriptions=result.database.entities[input.before.id].effects;
assert(descriptions.find(r=>r.模式==='PvE').描述.includes('人工PvE修订'));
assert(!descriptions.find(r=>r.模式==='PvP').描述.includes('人工PvP修订'));
assert.equal(editor.serialize().raw,raw);
process.stdout.write(JSON.stringify({raw,effectModule:'return '+catalog.lua(Object.fromEntries(database.references(result.database).map(r=>[r.id,r.modes])))}));
"""
        result=subprocess.run([shutil.which('node'),'-e',script],input=json.dumps({'before':before,'after':after}),text=True,encoding='utf8',capture_output=True,cwd=ROOT)
        self.assertEqual(result.returncode,0,result.stderr)
        from tools.equipment.wikitext import WikiSubset
        saved=json.loads(result.stdout)
        rendered=WikiSubset(ROOT,sources={'wiki/modules/TD2效果映射.lua':saved['effectModule']}).expand(saved['raw'],{})
        self.assertIn('人工PvE修订',rendered)
        self.assertNotIn('人工PvP修订',rendered)
        self.assertNotIn('td2-data-error',rendered)

    def test_real_memento_pvp_parameter_change_is_independent(self):
        n=Native(FIXTURE);r=n.record(TALENT,UID)
        pve=n.talent(r,'PvE');pvp=n.talent(r,'PvP')
        self.assertTrue(all(p['type'] in ('Percentage','FlatValue') for p in pvp[0]['parameters'].values()))
        changed=copy.deepcopy(r)
        parameters=[p for p in changed['properties'] if p['field']=='myValue' and any(c['resource_type']=='TalentOverride' for c in p['context'])]
        parameters[8]['raw_value']=str(float(parameters[8]['raw_value'])+0.01)
        self.assertEqual(n.talent(changed,'PvE'),pve)
        self.assertNotEqual(n.talent(changed,'PvP'),pvp)
        changed=copy.deepcopy(r)
        parameters=[p for p in changed['properties'] if p['field']=='myValue' and any(c['resource_type']=='TalentOverride' for c in p['context'])]
        parameters[4]['raw_value']='98765'
        self.assertEqual(n.talent(changed,'PvP'),pvp)

    def test_real_brand_modes_and_nested_dictionary_percentage(self):
        n=Native(FIXTURE);path='hunter/game system data/juice/item/gear_brand_set_511.mgearset'
        r=n.record(path,'4CDCE5B25C405137000321F5482F6F7B')
        for mode,value in [('PvE','12'),('PvP','10')]:
            semantic,rendered=n.bonus(r,'5D31260055F145480000064D6A3B97D0',1,mode)
            self.assertEqual(semantic['type'],'Percentage');self.assertEqual(rendered,value)

    def test_stable_attribute_slots_survive_reorder_and_preserve_other_fields(self):
        mapping=identity_catalog.read_json(ROOT/'data/equipment/native-map.json')
        entity=next(e for e in mapping['entities'] if e['id']=='exotic:346395bc5eff309f0003a7d41bab9c36')
        n=Native(FIXTURE);before=n.slots(entity['attribute_slots'],mapping)
        record=n.document(entity['attribute_slots']['source'])['resources'][0]
        record['properties'].reverse()
        after=n.slots(entity['attribute_slots'],mapping)
        self.assertEqual({r['id']:r['fields'] for r in before},{r['id']:r['fields'] for r in after})
        prop=next(p for p in record['properties'] if p['field']=='myPresetAttribute')
        prop['raw_value']='43A2C97052209A23000004CDD0FB54EC'
        changed=n.slots(entity['attribute_slots'],mapping)
        self.assertEqual({r['id'] for r in before},{r['id'] for r in changed})

    def test_missing_native_resource_emits_no_deletion_or_blank(self):
        result=Native(FIXTURE).project({'entities':[{'id':'missing','source':'wiki/pages/brands/test.wiki','template':'品牌套装信息','bindings':[{'source':'missing','uid':'missing','records':[],'fields':{'套装全称':{'kind':'text','property':'myUIName'}}}]}]})
        self.assertEqual(result['entities'][0]['units'],[]);self.assertEqual(len(result['unavailable']),1)

    def test_memento_talent_relation_is_followed_and_missing_target_is_unavailable(self):
        mapping=identity_catalog.read_json(ROOT/'data/equipment/native-map.json')
        entity=next(e for e in mapping['entities'] if e['id']=='exotic:346395bc5eff309f0003a7d41bab9c36')
        binding=next(b for b in bindings(entity) if b['kind']=='talent')
        n=Native(FIXTURE);self.assertEqual(n.bound_record(binding)['resource_uid'],UID)
        link=next(l for l in n.document(binding['follow'][0]['source'])['links'] if l['reference_uid']==binding['follow'][0]['reference_uid'])
        link['target_uid']='0'*32
        with self.assertRaisesRegex(ValueError,'target unavailable'):n.bound_record(binding)
