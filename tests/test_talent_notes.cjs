'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const domain=require('../ui/editor/src/mapped-domain.js'),fields=require('../ui/editor/src/page-fields.js');
const database=require('../tools/equipment/database.cjs'),projection=require('../tools/equipment/projection.cjs');
const catalog=projection.editor(database.load());
const hotshot='set:f58bdd56638db2e1000381f5e2a7136c',acosta='exotic:4cdce5b25be1b0b000032b512386d5e7';
function raw(id){return '{{'+catalog[id].template+'\n|资料ID='+id+'\n|其他机制=保留 [[链接]]\n}}\n人工正文';}
test('all registered talents expose independent stable keys without descriptions',()=>{
  for(const [id,e] of Object.entries(catalog)){
    const s=domain.create(raw(id));assert.deepEqual(s.blockers,[]);
    for(const t of e.talents||[]){assert(s.rules[fields.talentKey(t.id,t.mode)].label.endsWith(' · '+t.mode));assert(!s.rules[fields.talentKey(t.id,t.mode)].label.includes('{{'));assert(!Object.hasOwn(t,'description'));}
  }
});
test('existing note remains PvE only with unchanged manual text',()=>{
  const text=fs.readFileSync('wiki/pages/gear-sets/装备组-烈焰大炮.wiki','utf8'),s=domain.create(text);
  assert.deepEqual(s.blockers,[]);assert.equal(s.serialize().raw,text);
  const t=catalog[hotshot].talents.find(t=>t.name==='头痛欲裂'),key=fields.talentKey(t.id,'PvE');
  assert.equal(s.state.fields[key].value,'从第4次连续爆头开始，只有该次爆头击杀目标，才会同时获得三项奖励。');
  assert.equal(s.state.fields[fields.talentKey(t.id,'PvP')].value,null);
});
test('multi-talent roundtrip survives order and display-name changes without mode fallback',()=>{
  const s=domain.create(raw(acosta)),keys=catalog[acosta].talents.map(t=>fields.talentKey(t.id,t.mode));
  assert.equal(keys.length,4);keys.forEach((k,i)=>s.edit(k,'独立说明 '+i));
  const output=s.serialize().raw;assert(output.includes('|其他机制=保留 [[链接]]\n'));assert(output.endsWith('人工正文'));
  const changed=structuredClone(catalog);changed[acosta].talents.reverse().forEach(t=>t.name='更新后名称');
  const reopened=domain.create(output,{equipmentCatalog:changed});assert.deepEqual(reopened.blockers,[]);
  keys.forEach((k,i)=>assert.equal(reopened.state.fields[k].value,'独立说明 '+i));
  reopened.edit(keys[1],'');assert.equal(domain.create(reopened.serialize().raw).state.fields[keys[0]].value,'独立说明 0');
});
test('orphaned or foreign talent notes block save and remain protected from import',()=>{
  const s=domain.create(raw(acosta)),t=catalog[acosta].talents[0],key=fields.talentKey(t.id,t.mode);s.edit(key,'保留');
  const text=s.serialize().raw,changed=structuredClone(catalog);changed[acosta].talents=[];
  const orphan=domain.create(text,{equipmentCatalog:changed});assert(orphan.blockers.some(b=>b.code==='UNKNOWN_PARAMETER'));assert.throws(()=>orphan.serialize(),/SAVE_BLOCKED/);
  assert.equal(database.owned(database.load().entities[acosta],{field:key}),false);
  assert.equal(database.owned(database.load().entities[acosta],{field:'天赋脚注:removed:PvP'}),false);
  assert.throws(()=>domain.create(raw(hotshot)).edit(key,'x'),/READ_ONLY/);
});
