'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {plan,validatePage}=require('../tools/equipment/import.cjs');
const {key,fingerprint}=require('../tools/equipment/merge.cjs');
const {editor}=require('../tools/equipment/projection.cjs');
const {talentKey}=require('../ui/editor/src/page-fields.js');
const local=require('../ui/editor/src/local-session.js');
const json=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const stored=json('data/equipment/records.json');
const [id,entity]=Object.entries(stored.entities).find(([,e])=>e.fields.装备名称==='ACS-12');
const source=json('publishing/registry.json').entries.find(e=>e.related_entity===id&&e.kind==='pages').source;
const db={schema_version:1,entities:{[id]:{...entity,source}}};
const raw=fs.readFileSync(source,'utf8');
const rows=entity.collections.武器型号资料.rows;
const base=rows.find(r=>r.data.装备名称==='ACS-12').data;
const left=rows.find(r=>r.data.装备名称==='左边').data;
const donor=rows.find(r=>r.data.装备名称==='摇滚').data;
const effects=owner=>entity.effects.filter(e=>e.所属装备===owner.stable_id);
const model=(result,owner)=>result.database.entities[id].collections.武器型号资料.rows.find(r=>r.stable_id===owner.stable_id).data;
function input(row,talents=effects(row)){
  const target={field:'data',records:[{field:'武器型号资料',template:'武器型号',id:{stable_id:row.stable_id}}]};
  const units=[{target,value:JSON.stringify(row),semantic:row,fixed_effect_ids:[...new Set(talents.map(t=>t.效果ID))]}];
  for(const t of talents){
    const records=[{field:'效果资料',template:'装备效果',id:{效果ID:t.效果ID,模式:t.模式}}];
    for(const [field,value] of Object.entries(t))units.push({target:{records,field},value,semantic:value});
  }
  return {schema_version:1,entities:[{id,source,template:'武器信息',units}],unavailable:[]};
}
const run=(incoming,baseline=legacy,records=db,text=raw)=>plan(incoming,baseline,()=>text,records,{});
const legacyUnits=rows.flatMap(r=>input(r.data).entities[0].units).map(u=>[key(u.target),fingerprint(u.semantic)]);
const legacy={schema_version:1,projection_version:1,entities:{[id]:{units:Object.fromEntries(legacyUnits)}}};
const note=(t)=>talentKey(t.效果ID,t.模式);
const editorInputs=result=>({catalog:[],options:{equipmentCatalog:editor(result.database)}});

test('a native rename changes only its language and preserves the other label and UID page',()=>{
  const previous=structuredClone(legacy), records=structuredClone(db);
  for(const field of ['装备名称','英文原名'])
    previous.entities[id].units[key({field,records:[]})]=fingerprint(entity.fields[field]);
  model({database:records},base).description='人工简介';
  const next={...base,装备名称:'测试新名'};
  delete next.英文原名;
  const incoming=input(next);
  incoming.entities[0].units.push({target:{field:'装备名称',records:[]},value:next.装备名称,semantic:next.装备名称});
  incoming.unavailable.push({uid:base.装备UID,field:'英文原名',reason:'fixture missing the English translation'});
  const result=run(incoming,previous,records);
  assert(!result.unavailable.some(i=>i.field==='model_baseline'));
  const updated=model(result,base);
  assert.equal(updated.装备名称,next.装备名称);assert.equal(updated.英文原名,base.英文原名);
  assert.equal(updated.description,'人工简介');assert.equal(updated.stable_id,base.stable_id);
  const fields=result.database.entities[id].fields;
  assert.equal(fields.装备名称,next.装备名称);assert.equal(fields.英文原名,entity.fields.英文原名);
  assert.equal(result.pages[0].source,source);assert.equal(result.pages[0].raw,raw);
  assert.deepEqual(run(incoming,result.baseline,result.database).database,result.database);
});

test('ACS-12 migrates its aggregate fingerprint without losing a correction or failed attribute input',()=>{
  const records=structuredClone(db),current=model({database:records},base);
  current.description='人工简介';
  const changed=structuredClone(base);changed.attributes=[];changed.stats.headshot=0;changed.stats.rpm+=1;
  const incoming=input(changed);incoming.unavailable.push({uid:base.装备UID,field:'attributes',reason:'missing input'});
  const result=run(incoming,legacy,records),merged=model(result,base);
  assert.equal(merged.description,'人工简介');assert.equal(base.attributes.length,3);
  assert.deepEqual(merged.attributes,base.attributes);assert.equal(merged.stats.headshot,base.stats.headshot);
  assert.equal(merged.stats.rpm,changed.stats.rpm);
  const state=result.baseline.entities[id];
  assert.equal(result.baseline.projection_version,2);
  assert.equal(state.units[key(incoming.entities[0].units[0].target)],undefined);
  assert.equal(state.weaponModels[base.stable_id].attributes,fingerprint(base.attributes));
  assert.deepEqual(run(incoming,result.baseline,result.database).database,result.database);
  const restored=input({...changed,attributes:base.attributes,stats:{...changed.stats,headshot:base.stats.headshot}});
  assert.deepEqual(run(restored,result.baseline,result.database).database,result.database);
  const cleared=run(input({...base,attributes:[]}),result.baseline,result.database);
  assert.deepEqual(model(cleared,base).attributes,[]);assert.equal(model(cleared,base).description,'人工简介');
});

test('fixed RPM survives an unavailable attachment until its removal is confirmed',()=>{
  const rated=structuredClone(base);
  rated.stats.rpm_with_mods=base.stats.rpm*1.1;
  rated.stats.dps=base.stats.dps*1.1;
  const first=run(input(rated));
  const removal=input(base);
  removal.entities[0].units[0].clear=['stats.rpm_with_mods'];
  removal.unavailable.push({uid:base.装备UID,field:'sockets',reason:'unavailable attachment'});
  const held=run(removal,first.baseline,first.database);
  assert.equal(model(held,base).stats.rpm_with_mods,rated.stats.rpm_with_mods);
  assert.equal(model(held,base).stats.dps,rated.stats.dps);
  removal.unavailable=[];
  const confirmed=run(removal,held.baseline,held.database);
  assert(!Object.hasOwn(model(confirmed,base).stats,'rpm_with_mods'));
  assert.equal(model(confirmed,base).stats.dps,base.stats.dps);
});

test('distance damage survives missing native inputs and an explicit empty physical mode can replace it',()=>{
  const first=run(input(base));
  const special=structuredClone(base);
  special.stats.distance_damage=[];
  const change=input(special);
  assert(base.stats.distance_damage.length);
  for(const field of ['distance_damage','sockets','attributes']){
    change.unavailable=[{uid:base.装备UID,field,reason:'missing native input'}];
    const held=run(change,first.baseline,first.database);
    assert.deepEqual(model(held,base).stats.distance_damage,base.stats.distance_damage);
  }
  change.unavailable=[];
  const confirmed=run(change,first.baseline,first.database);
  assert.deepEqual(model(confirmed,base).stats.distance_damage,[]);
  assert.equal(model(confirmed,base).stats.stability_compare,base.stats.stability_compare);
});

test('an incomplete update keeps the calibrated damage, precision and DPS interval together',()=>{
  const estimated=structuredClone(base);
  Object.assign(estimated.stats,{base_damage:59999.2,damage_precision:10,dps:600000,dps_range:[599000,601000]});
  const first=run(input(estimated));
  const exact=input(base);
  exact.entities[0].units[0].clear=['stats.damage_precision','stats.dps_range'];
  exact.unavailable.push({uid:base.装备UID,field:'attributes',reason:'fixed grant unavailable'});
  const held=run(exact,first.baseline,first.database);
  assert.deepEqual(model(held,base).stats,estimated.stats);
  exact.unavailable=[];
  const retried=run(exact,held.baseline,held.database);
  assert.deepEqual(model(retried,base).stats,base.stats);
});

test('an unreadable primary damage curve preserves the volley, panel and DPS until a successful retry',()=>{
  const previous=structuredClone(base);
  Object.assign(previous.stats,{base_damage:60000,damage_ui:60000,dps:300000});
  const first=run(input(previous));
  const partial=structuredClone(base);
  const keys=['base_damage','damage_ui','dps'];
  for(const k of keys)delete partial.stats[k];
  const update=input(partial);
  update.entities[0].units[0].clear=keys.map(k=>'stats.'+k);
  update.unavailable.push({uid:base.装备UID,field:'base_damage',reason:'missing native curve'});
  const held=run(update,first.baseline,first.database);
  assert.deepEqual(model(held,base).stats,previous.stats);
  const retry=run(input(base),held.baseline,held.database);
  assert.deepEqual(model(retry,base).stats,base.stats);
  assert.deepEqual(run(input(base),retry.baseline,retry.database).baseline,retry.baseline);
});

test('first baseline, unexplained omission, explicit deletion and ambiguous migration stay distinct',()=>{
  const records=structuredClone(db),current=model({database:records},base);current.stats.rpm=-1;
  const first=run(input(base),null,records);
  assert.equal(model(first,base).stats.rpm,-1);
  const native=structuredClone(base);delete native.stats.dps;
  const incoming=input(native);
  const omitted=run(incoming,first.baseline,first.database);
  assert.equal(model(omitted,base).stats.dps,base.stats.dps);
  incoming.entities[0].units[0].clear=['stats.dps'];
  const cleared=run(incoming,omitted.baseline,omitted.database);
  assert(!Object.hasOwn(model(cleared,base).stats,'dps'));
  assert.deepEqual(run(incoming,cleared.baseline,cleared.database).baseline,cleared.baseline);
  const ambiguous=structuredClone(legacy),aggregate=key(incoming.entities[0].units[0].target);
  ambiguous.entities[id].units[aggregate]=fingerprint('unavailable historical model');
  const held=run(incoming,ambiguous,records);
  assert(held.unavailable.some(x=>x.field==='model_baseline'));
  assert.deepEqual(held.database,records);assert.deepEqual(held.baseline,ambiguous);
});

function replacement(){
  return effects(donor).map(t=>({...t,所属装备:left.stable_id,效果ID:t.效果ID.replace(donor.stable_id,left.stable_id)}));
}
test('fixed-to-fixed replacement retires only the old pair and preserves the exact orphan note and body',()=>{
  const old=effects(left),newRows=replacement(),incoming=input(left,newRows),oldKey=note(old[0]);
  const text=raw.replace('|资料ID=','|'+oldKey+'=保留 [[人工说明]]\n|资料ID=')+'\n人工正文';
  const result=run(incoming,legacy,db,text),record=result.database.entities[id];
  assert.deepEqual(record.effects.filter(t=>t.所属装备===left.stable_id),newRows);
  assert.deepEqual(record.effects.filter(t=>t.所属装备!==left.stable_id),entity.effects.filter(t=>t.所属装备!==left.stable_id));
  const inputs=editorInputs(result),page=result.pages[0];
  assert.deepEqual(inputs.options.equipmentCatalog[id].talents.filter(t=>t.id.startsWith(left.stable_id+'_')).map(t=>t.mode),['PvE','PvP']);
  assert.deepEqual(page.orphanNotes,[oldKey]);assert.equal(page.raw,text);validatePage(page,inputs);
  const s=local.create(text,[],inputs.options);assert.throws(()=>s.serialize(),/SAVE_BLOCKED/);
  assert.throws(()=>validatePage({...page,raw:text.replace('|资料ID=','|陌生参数=x\n|资料ID=')},inputs),/Invalid imported structure/);
  assert(!Object.keys(result.baseline.entities[id].units).some(k=>k.includes(old[0].效果ID)));
  const again=run(incoming,result.baseline,result.database,text);
  assert.deepEqual(again.baseline,result.baseline);assert.deepEqual(again.database,result.database);validatePage(again.pages[0],inputs);
  const restored=run(input(left),again.baseline,again.database,text);
  assert(!restored.pages[0].orphanNotes);assert.equal(local.create(text,[],editorInputs(restored).options).serialize().raw,text);
});

test('only a complete resolved random slot can retire both fixed modes',()=>{
  const random={...left,random_talent:true,fixed_talent_bonuses:{}},incoming=input(random,[]);
  const retired=run(incoming);
  assert.equal(model(retired,left).random_talent,true);
  assert.equal(retired.database.entities[id].effects.filter(e=>e.所属装备===left.stable_id).length,0);
  for(const field of ['talents','talent:'+donor.装备UID+':PvP']){
    const partial=input(random,replacement().slice(0,1));
    delete partial.entities[0].units[0].fixed_effect_ids;
    partial.unavailable=[{uid:left.装备UID,field,reason:'fixture missing input'}];
    const held=run(partial);
    assert.deepEqual(held.database.entities[id].effects,entity.effects);
    assert.equal(model(held,left).random_talent,false);
  }
  const incomplete=input(left,replacement().slice(0,1));
  assert.throws(()=>run(incomplete),/Incomplete fixed talent/);
  const first=run(incoming,null);
  assert(first.unavailable.some(issue=>issue.field==='talents'));
  assert.deepEqual(first.database.entities[id].effects,entity.effects);assert.equal(model(first,left).random_talent,false);
});
