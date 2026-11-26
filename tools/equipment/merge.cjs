'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto');
const page=require('./page.cjs');
function canonical(value){return Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;}
const fingerprint=value=>crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const key=target=>JSON.stringify(canonical({...target,records:(target.records||[]).map(({field,id})=>({field,id}))}));
function merge(raw,previous,incoming){
  assert.equal(incoming.schema_version,1);assert(Array.isArray(incoming.units));
  const seen=new Set(),changes=[],units={...(previous?.units||{})},first=!previous;
  const current=page.read(raw);
  for(const unit of incoming.units){
    const id=key(unit.target);assert(!seen.has(id),'Duplicate native target');seen.add(id);
    assert(typeof unit.value==='string'&&unit.semantic!==undefined,'Incomplete native unit');
    const digest=fingerprint(unit.semantic),old=units[id];
    const value=page.value(current,unit.target);
    if((!first&&old!==undefined||value===undefined)&&old!==digest&&value!==unit.value)changes.push(unit);
    units[id]=digest;
  }
  return {raw:page.update(raw,changes),baseline:{units},changes:changes.map(({target})=>target),initialized:first};
}
function reconcile(base,local,remote,targets){
  const b=page.read(base),l=page.read(local),r=page.read(remote),changes=[],conflicts=[];
  for(const target of targets){
    const before=page.value(b,target),here=page.value(l,target),there=page.value(r,target);
    if(there===undefined||there===before||there===here)continue;
    if(here!==before)conflicts.push(target);else changes.push({target,value:there});
  }
  return {raw:conflicts.length?local:page.update(local,changes),conflicts};
}
module.exports={merge,reconcile,fingerprint,key};
