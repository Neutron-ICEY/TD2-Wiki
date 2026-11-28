'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {plan,cell}=require('../tools/equipment/catalog-import.cjs');
const file='data/equipment/crafting.json';
const unit=(path,value,semantic=value)=>({file,path,value,semantic});
test('a new native pool preserves precision of equal fixed-preset display values',()=>{
  const file='data/brand-sets/fixed-minor-presets.json';
  const path=['presets','example','value'];
  const start=plan([{file,path,value:'50.0',semantic:{pool:'previous',value:50}}],null,{});
  const change=(value,amount)=>plan([{file,path,value,semantic:{pool:'current',value:amount}}],start.hashes,start.catalogs);
  assert.equal(change('50',50).catalogs[file].presets.example.value,'50.0');
  assert.equal(change('51',51).catalogs[file].presets.example.value,'51');
});
test('catalog baseline preserves human corrections until that exact native field changes',()=>{
  const current={[file]:{schema_version:1,blueprints:{A:{name:'人工修订',targets:['X'],guide:'独立说明'}}}};
  const first=plan([unit(['blueprints','A','name'],'游戏旧名')],null,current);
  assert.equal(first.catalogs[file].blueprints.A.name,'人工修订');assert.equal(first.changes.length,0);
  const repeat=plan([unit(['blueprints','A','name'],'游戏旧名')],first.hashes,first.catalogs);assert.deepEqual(repeat,first);
  const update=plan([unit(['blueprints','A','name'],'游戏新名')],first.hashes,first.catalogs);
  assert.deepEqual(update.catalogs[file].blueprints.A,{name:'游戏新名',targets:['X'],guide:'独立说明'});
  const missing=plan([],update.hashes,update.catalogs);assert.deepEqual(missing.catalogs,update.catalogs);assert.deepEqual(missing.hashes,update.hashes);
});
test('membership changes replace a relationship group without stale candidates',()=>{
  const a=plan([unit(['blueprints','B','targets'],['A','B'])],null,{});
  const b=plan([unit(['blueprints','B','targets'],['C'])],a.hashes,a.catalogs);
  assert.deepEqual(b.catalogs[file].blueprints.B.targets,['C']);
  assert.throws(()=>plan([unit(['__proto__','polluted'],true)],null,{}),/Invalid catalog key/);
  assert.throws(()=>plan([{file:'wiki/pages/unsafe.wiki',path:['x'],value:1,semantic:1}],null,{}),/Unregistered/);
});
test('shared array fields update by stable identity and duplicate identities fail closed',()=>{
  const data={rows:[{id:'b',name:'B'},{id:'a',name:'A'}]};assert.equal(cell(data,['rows',{key:'id',value:'a'},'name']).obj.name,'A');
  data.rows.push({id:'a',name:'Another'});assert.throws(()=>cell(data,['rows',{key:'id',value:'a'},'name']),/Ambiguous/);
});
