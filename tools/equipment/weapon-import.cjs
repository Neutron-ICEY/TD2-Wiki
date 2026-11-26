'use strict';
const assert=require('node:assert/strict');
const database=require('./database.cjs');
const {key,fingerprint}=require('./merge.cjs');
const {talentKey}=require('../../ui/editor/src/page-fields.js');

const isModel=target=>target.field==='data'&&target.records?.length===1&&target.records[0].field==='武器型号资料';
const derived=['stats.headshot','stats.stability_compare','stats.reload_ui','stats.reload_with_mods','stats.reload_empty_with_mods',
  'stats.rpm_with_mods','stats.damage_with_mods','stats.damage_ui','stats.default_damage_pending','stats.optimal_with_mods','stats.long_with_mods','stats.distance_damage',
  'stats.fixed_secondary','stats.fire_cycle','stats.dps','stats.dps_range','stats.pellets_with_mods','stats.magazine_with_mods','stats.accuracy_compare','stats.reload_unnecessary'];
function protectedFields(missing,completeTalents){
  const held=new Set();
  for(const {field} of missing){
    if(field==='attributes') ['attributes',...derived].forEach(f=>held.add(f));
    else if(field==='sockets'||field.startsWith('mod:')) ['sockets','skins',...derived].forEach(f=>held.add(f));
    else if(field==='base_damage') ['stats.base_damage','stats.damage_with_mods','stats.damage_ui','stats.damage_precision','stats.dps','stats.dps_range','stats.fire_cycle'].forEach(f=>held.add(f));
    else if(field==='signature_discharge') ['stats.base_explosion_damage','stats.dps','stats.dps_range'].forEach(f=>held.add(f));
    else if(field==='myAimDirectionRecoil'||field==='myCameraRecoil')held.add('recoil');
    else if(field==='reload_ui')['stats.reload_ui','stats.reload_with_mods','stats.reload_empty_with_mods'].forEach(f=>held.add(f));
    else if(field==='stability_compare')held.add('stats.stability_compare');
    else if(field==='distance_damage')held.add('stats.distance_damage');
    else if(['装备名称','英文原名','description','skins','expertise'].includes(field))held.add(field);
  }
  if(!completeTalents)
    ['random_talent','fixed_talent_bonuses',...derived].forEach(f=>held.add(f));
  return held;
}

// Collections are one semantic value. Independent numeric stats have separate fingerprints.
function flatten(row){
  const values=new Map();
  for(const [name,value] of Object.entries(row)){
    if(name==='stats')for(const [stat,v] of Object.entries(value))values.set('stats.'+stat,v);
    else values.set(name,value);
  }
  return values;
}
function assign(row,field,value){
  assert(/^(?:stats\.)?[^.]+$/u.test(field),'Invalid weapon field path');
  const stat=field.startsWith('stats.'),name=stat?field.slice(6):field;
  assert(!['__proto__','constructor','prototype','stats'].includes(name),'Invalid weapon field');
  const dest=stat?(row.stats??={}):row;
  if(value===undefined)delete dest[name];
  else dest[name]=structuredClone(value);
}
function legacyValues(current,incoming,held,old){
  if(fingerprint(current)===old)return flatten(current);
  if(fingerprint(incoming)===old)return flatten(incoming);
  // Trust a reconstructed ancestor only when its entire old digest matches.
  const local=flatten(current),native=flatten(incoming),candidate=structuredClone(incoming);
  for(const field of held)assign(candidate,field,local.get(field));
  if(fingerprint(candidate)===old)return flatten(candidate);
  for(const field of new Set([...local.keys(),...native.keys()])){
    if(held.has(field)||fingerprint(local.get(field)??null)===fingerprint(native.get(field)??null))continue;
    assign(candidate,field,local.get(field));
    if(fingerprint(candidate)===old)return flatten(candidate);
    assign(candidate,field,native.get(field));
  }
  // One local correction can also coexist with several independent native changes.
  const fromLocal=structuredClone(current);
  for(const [field,value] of native){
    if(held.has(field)||fingerprint(local.get(field)??null)===fingerprint(value))continue;
    assign(fromLocal,field,value);
    if(fingerprint(fromLocal)===old)return flatten(fromLocal);
    assign(fromLocal,field,local.get(field));
  }
  return null;
}

function model(record,unit,units,models,issues){
  const next=unit.semantic,owner=unit.target.records[0].id.stable_id,aggregate=key(unit.target);
  assert.equal(owner,next.stable_id);
  assert.equal(owner,'weapon_'+next.装备UID.toLowerCase());
  assert.deepEqual(JSON.parse(unit.value),next,'Inconsistent weapon model payload');
  const missing=issues.filter(issue=>issue.uid===next.装备UID);
  const failedTalents=missing.some(({field})=>field==='talents'||field.startsWith('talent:'));
  let complete=Array.isArray(unit.fixed_effect_ids)&&!failedTalents;
  if(!complete&&!failedTalents)
    issues.push({uid:next.装备UID,field:'talents',reason:'Regenerate weapon projection to establish fixed talent membership'});
  if(complete){
    for(const row of record.effects){
      if(row.所属装备!==owner||(unit.fixed_effect_ids.includes(row.效果ID)&&['PvE','PvP'].includes(row.模式)))continue;
      const step={field:'效果资料',id:{效果ID:row.效果ID,模式:row.模式}};
      if(units[key({records:[step],field:'所属装备'})]!==fingerprint(owner)){
        issues.push({uid:next.装备UID,field:'talents',reason:'Untracked existing effect requires review: '+row.效果ID});
        complete=false;
        break;
      }
    }
  }
  const held=protectedFields(missing,complete);
  const current=database.value(record,unit.target),result=structuredClone(current||{}),fields=[];
  if (held.has('stats.dps') && (current?.stats?.damage_precision || next.stats?.damage_precision)) {
    // An existing default DPS and its reported precision must move together on retry.
    held.add('stats.base_damage');
    held.add('stats.damage_precision');
  }
  const hashes=current?{...models[owner]}:{};
  if(units[aggregate]&&current){
    const old=legacyValues(current,next,held,units[aggregate]);
    if(!old){
      issues.push({uid:next.装备UID,field:'model_baseline',reason:'Cannot verify previous model from whole-row fingerprint'});
      return {owner,complete:false,fields};
    }
    for(const [field,value] of old)hashes[field]=fingerprint(value);
  }
  const local=flatten(result),native=flatten(next);
  for(const field of unit.clear||[]){
    assert(!native.has(field),'Weapon field is both present and cleared');
    native.set(field,undefined);
  }
  for(const [field,value] of native){
    if(held.has(field))continue;
    const old=hashes[field],digest=value===undefined?undefined:fingerprint(value);
    const has=local.has(field);
    if((old!==undefined||!has)&&old!==digest&&(value===undefined?has:!has||fingerprint(local.get(field))!==digest)){
      assign(result,field,value);
      fields.push({...unit.target,path:field});
    }
    if(digest===undefined)delete hashes[field];
    else hashes[field]=digest;
  }
  if(fields.length)database.write(record,unit.target,JSON.stringify(result));
  models[owner]=hashes;
  delete units[aggregate];
  return {owner,complete,ids:unit.fixed_effect_ids,random:next.random_talent,fields};
}

// Validate both modes before treating the projected slot as authoritative.
function effects(record,models,effectUnits,units,notes,fields){
  const permitted=new Set();
  const targets=new Map();
  for(const unit of effectUnits){
    const {效果ID:id,模式:mode}=unit.target.records[0].id;
    const pair=talentKey(id,mode);
    if(!targets.has(pair))targets.set(pair,new Map());
    targets.get(pair).set(unit.target.field,unit.value);
  }
  for(const {owner,complete,ids,random} of models){
    if(!complete)continue;
    assert.equal(random,ids.length===0,'Inconsistent fixed talent slot');
    assert.equal(new Set(ids).size,ids.length,'Duplicate fixed talent');
    const members=new Set();
    for(const id of ids){
      assert(id.startsWith(owner+'_')&&/^[a-f0-9]{32}$/.test(id.slice(owner.length+1)),'Invalid fixed talent ID');
      for(const mode of ['PvE','PvP']){
        const pair=talentKey(id,mode),row=targets.get(pair);
        assert(row?.get('所属装备')===owner&&row.get('效果ID')===id&&row.get('模式')===mode&&row.get('名称')&&row.get('描述'),'Incomplete fixed talent: '+pair);
        const current=record.effects.find(effect=>effect.效果ID===id&&effect.模式===mode);
        if(current)assert.equal(current.所属装备,owner,'Fixed talent owner changed');
        else {
          const step={field:'效果资料',id:{效果ID:id,模式:mode}};
          for(const field of row.keys())delete units[key({records:[step],field})];
        }
        permitted.add(pair);members.add(pair);notes.delete(pair);
      }
    }
    for(const [pair,row] of targets)if(row.get('所属装备')===owner)assert(members.has(pair),'Unexpected fixed talent');
    const retired=new Set();
    record.effects=record.effects.filter(row=>{
      const {效果ID:id,模式:mode}=row,pair=talentKey(id,mode);
      if(row.所属装备!==owner||members.has(pair))return true;
      const step={field:'效果资料',id:{效果ID:id,模式:mode}};
      retired.add(pair);notes.add(pair);fields.push({records:[step],removed:true});return false;
    });
    if(retired.size)for(const name of Object.keys(units)){
      const step=JSON.parse(name).records?.[0];
      if(step?.field==='效果资料'&&retired.has(talentKey(step.id.效果ID,step.id.模式)))delete units[name];
    }
  }
  return permitted;
}
module.exports={isModel,model,effects};
