'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const database=require('../tools/equipment/database.cjs'),{plan}=require('../tools/equipment/import.cjs'),effects=require('../ui/editor/src/page-effects.js'),page=require('../tools/equipment/page.cjs'),local=require('../ui/editor/src/local-session.js'),catalog=require('../tools/equipment/catalog.cjs').data();
const db=database.load(),source='wiki/pages/exotic-gear/奇特装备-追悼.wiki',id=Object.keys(db.entities).find(k=>db.entities[k].source===source),raw=fs.readFileSync(source,'utf8');
const target=(row,field)=>({field,records:[{field:'效果资料',id:{效果ID:row.效果ID,模式:row.模式},template:'装备效果'}]});
const unit=(row,field)=>({target:target(row,field),value:row[field],semantic:row[field]});
const rows=db.entities[id].effects;
const entity={id,source,template:'奇特装备信息',units:rows.map(r=>unit(r,'描述'))};

test('named talent projection validates current effect relationships without rendering pages',()=>{
  const projection=require('../tools/equipment/projection.cjs');
  for(const record of Object.values(db.entities))if(record.collections?.具名装备资料)assert.doesNotThrow(()=>projection.named(record));
});

test('named talent projection rejects missing or mismatched effects and empty content',()=>{
  const projection=require('../tools/equipment/projection.cjs');
  const source=Object.values(db.entities).find(e=>e.fields.套装全称==='5.11 Tactical');
  for(const change of [
    (e,row)=>{delete row.天赋引用;},
    (e,row)=>{row.天赋引用='unknown';},
    (e,row)=>{e.effects=e.effects.filter(effect=>effect.所属装备!==row.stable_id);},
    (e,row)=>{e.effects.find(effect=>effect.所属装备===row.stable_id&&effect.模式==='PvP').所属装备='wrong_owner';},
    (e,row)=>{e.effects.find(effect=>effect.所属装备===row.stable_id&&effect.模式==='PvP').效果ID='wrong_effect';},
    (e,row)=>{e.effects.find(effect=>effect.所属装备===row.stable_id).名称='';},
    (e,row)=>{e.effects.find(effect=>effect.所属装备===row.stable_id).描述=' ';},
  ]){
    const record=structuredClone(source),row=record.collections.具名装备资料.rows.find(r=>r.talent_mode==='fixed');
    change(record,row);
    assert.throws(()=>projection.named(record),new RegExp('具名装备天赋效果关联无效: '+row.stable_id));
  }
});

test('an incoming entity cannot update a page that refers to another identity',()=>{
  assert.throws(()=>plan({schema_version:1,entities:[entity]},null,()=>raw.replace(id,'exotic:other'),db),/Page identity mismatch/);
});
test('fixed data has one maintained home; all page references resolve',()=>{
  for(const [id,record] of Object.entries(db.entities)){
    const p=page.read(fs.readFileSync(record.source,'utf8')),refs=effects.read(p.root.fields.效果资料?.value||'');
    for(const row of refs){assert(row.引用);assert(database.references(db).some(r=>r.id===row.引用&&r.modes[row.模式]));for(const f of effects.mappedFields)assert.equal(row[f],undefined);}
    for(const f of [...Object.keys(record.fields),'属性槽'])assert.equal(p.root.fields[f],undefined);
    if(record.template==='奇特装备信息')assert(record.slots.length);
  }
});
test('database first baseline preserves manual values, unchanged native stays, changed PvP updates only PvP',()=>{
  const initial=plan({schema_version:1,entities:[entity]},null,()=>raw,db);assert.equal(initial.pages[0].raw,raw);
  const manual=structuredClone(initial.database);for(const r of manual.entities[id].effects)r.描述+=' manual '+r.模式;
  const unchanged=plan({schema_version:1,entities:[entity]},initial.baseline,p=>p===source?raw:null,manual);assert.deepEqual(unchanged.database,manual);
  const next=structuredClone(entity);next.units[1].value+=' native update';next.units[1].semantic+=' native update';
  const changed=plan({schema_version:1,entities:[next]},initial.baseline,p=>p===source?raw:null,manual);
  assert.equal(changed.database.entities[id].effects[0].描述,manual.entities[id].effects[0].描述);assert.equal(changed.database.entities[id].effects[1].描述,next.units[1].value);assert.equal(changed.pages[0].raw,raw);
  const missing=plan({schema_version:1,entities:[{...entity,units:[]}]},initial.baseline,p=>p===source?raw:null,manual);assert.deepEqual(missing.database,manual);
});

test('new field baseline preserves existing corrections; genuinely new records import without touching neighbors',()=>{
  const incoming=structuredClone(entity),first=plan({schema_version:1,entities:[incoming]},null,()=>raw,db);
  const extra={target:{field:'英文原名'},value:'Native English',semantic:'Native English'};incoming.units.push(extra);
  const result=plan({schema_version:1,entities:[incoming]},first.baseline,()=>raw,first.database);
  assert.equal(result.database.entities[id].fields.英文原名,db.entities[id].fields.英文原名);
  incoming.units.at(-1).value='Changed English';incoming.units.at(-1).semantic='Changed English';
  const changed=plan({schema_version:1,entities:[incoming]},result.baseline,()=>raw,result.database);assert.equal(changed.database.entities[id].fields.英文原名,'Changed English');
  const added=structuredClone(incoming.units[0]);added.target.records[0].id.效果ID='new_effect';incoming.units.push(added);
  const next=plan({schema_version:1,entities:[incoming]},changed.baseline,()=>raw,changed.database);
  assert.equal(next.pages[0].raw,raw);assert(next.database.entities[id].effects.some(r=>r.效果ID==='new_effect'));assert.deepEqual(next.database.entities[id].slots,db.entities[id].slots);
});

test('first baseline fills absent fixed fields while preserving existing values',()=>{
  const records=structuredClone(db);delete records.entities[id].fields.英文原名;
  const incoming={...entity,units:[...entity.units,{target:{field:'英文原名'},value:'Memento',semantic:'Memento'}]};
  const result=plan({schema_version:1,entities:[incoming]},null,()=>raw,records);
  assert.equal(result.database.entities[id].fields.英文原名,'Memento');
  assert.deepEqual(result.database.entities[id].effects,db.entities[id].effects);assert.equal(result.pages[0].raw,raw);
});
