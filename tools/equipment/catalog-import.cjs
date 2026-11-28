'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {fingerprint,key}=require('./merge.cjs');
const files=['data/equipment/crafting.json','data/brand-sets/acquisition-methods.json','data/brand-sets/equipment-base-rules.json','data/brand-sets/equipment-ui.json','data/gear-sets/sets.json','data/gear-sets/dismantle-rules.json'];
files.push('data/equipment/attributes.json','data/brand-sets/minor-attributes.json','data/brand-sets/fixed-minor-presets.json');
function load(root){return Object.fromEntries(files.map(file=>[file,fs.existsSync(path.join(root,file))?JSON.parse(fs.readFileSync(path.join(root,file),'utf8')):null]));}
function cell(root,steps,create=false){
  assert(Array.isArray(steps)&&steps.length,'Empty catalog target');let obj=root;
  for(let i=0;i<steps.length;i++){
    const step=steps[i];let k=step;
    if(typeof step==='object'){
      assert(step&&typeof step.key==='string'&&typeof step.value==='string'&&Array.isArray(obj),'Invalid catalog identity');
      const matches=obj.map((r,n)=>r[step.key]===step.value?n:-1).filter(n=>n>=0);assert(matches.length<=1,'Ambiguous catalog identity');
      k=matches[0];if(k===undefined){if(!create)return null;k=obj.length;obj.push({[step.key]:step.value});}
    }else assert(typeof k==='string'&&!['__proto__','prototype','constructor'].includes(k),'Invalid catalog key');
    if(i===steps.length-1)return {obj,key:k};
    if(obj[k]===undefined){if(!create)return null;obj[k]=typeof steps[i+1]==='object'?[]:{};}
    assert(obj[k]&&typeof obj[k]==='object','Catalog target crosses a scalar');obj=obj[k];
  }
}
function plan(units,baseline,current){
  const catalogs=structuredClone(current),hashes={...(baseline||{})},changes=[],seen=new Set();
  for(const unit of units||[]){
    assert(files.includes(unit.file),'Unregistered native catalog: '+unit.file);
    assert(unit.value!==undefined&&unit.semantic!==undefined,'Incomplete catalog unit');
    const id=key({file:unit.file,path:unit.path});assert(!seen.has(id),'Duplicate catalog target');seen.add(id);
    const document=catalogs[unit.file]??={schema_version:1},before=cell(document,unit.path),value=before?.obj[before.key],digest=fingerprint(unit.semantic);
    const samePresetValue=unit.file==='data/brand-sets/fixed-minor-presets.json'&&unit.path[0]==='presets'&&unit.path.at(-1)==='value'&&
      [value,unit.value].every(v=>typeof v==='string'&&/^-?\d+(?:\.\d+)?$/.test(v))&&Number(value)===Number(unit.value);
    if((value===undefined||hashes[id]!==undefined)&&hashes[id]!==digest&&!samePresetValue&&fingerprint(value??null)!==fingerprint(unit.value)){
      const target=cell(document,unit.path,true);target.obj[target.key]=structuredClone(unit.value);changes.push({file:unit.file,path:unit.path});
    }
    hashes[id]=digest;
  }
  if(units?.length&&catalogs['data/equipment/crafting.json']?.currencies){
    const names=catalogs['data/equipment/crafting.json'].currencies;
    const gear=catalogs['data/gear-sets/dismantle-rules.json'];
    const ids=Object.fromEntries([...(gear?.common.fixed_materials||[]),...(gear?.common.chance_materials||[]),...Object.values(gear?.slots||{}).flat()].map(r=>[r.id,r.currency_uid]));
    const assign=(file,steps,name)=>{const target=cell(catalogs[file],steps,true);if(target.obj[target.key]!==name){target.obj[target.key]=name;changes.push({file,path:steps,derived:true});}};
    const native=catalogs['data/equipment/crafting.json'];
    for(const row of catalogs['data/gear-sets/sets.json']?.sets||[]){
      const at=['sets',{key:'id',value:row.id},'material'],uid=native.materials?.[row.id]?.currency_uid||row.material?.currency_uid;
      if(!row.material)continue;
      if(uid)assign('data/gear-sets/sets.json',[...at,'currency_uid'],uid);
      const name=names[uid]?.name;if(name)assign('data/gear-sets/sets.json',[...at,'name'],name);
    }
    const groups=[];
    for(const [slot,data] of Object.entries(catalogs['data/brand-sets/equipment-base-rules.json']?.部位||{}))for(const group of ['fixed_materials','chance_materials'])groups.push(['data/brand-sets/equipment-base-rules.json',['部位',slot,'dismantle',group],data.dismantle[group]]);
    for(const group of ['fixed_materials','chance_materials'])groups.push(['data/gear-sets/dismantle-rules.json',['common',group],gear?.common[group]||[]]);
    for(const [slot,rows] of Object.entries(gear?.slots||{}))groups.push(['data/gear-sets/dismantle-rules.json',['slots',slot],rows]);
    for(const [file,steps,rows] of groups)for(const row of rows){const name=names[row.currency_uid||ids[row.id]]?.name;if(name)assign(file,[...steps,{key:'id',value:row.id},'name'],name);}
    for(const [key,row] of Object.entries(catalogs['data/brand-sets/equipment-ui.json']?.material_display||{})){
      const owners=new Set(Object.values(native.items||{}).filter(i=>row.native&&i.brand_uid===row.native.gearbrand_uid).map(i=>i.entity_id));
      const mapped=owners.size===1?native.materials?.[[...owners][0]]?.currency_uid:null;
      const uid=mapped||row.native?.currency_uid||ids[row.icon_key],name=names[uid]?.name;
      if(mapped)assign('data/brand-sets/equipment-ui.json',['material_display',key,'native','currency_uid'],mapped);
      if(name&&name!==row.name)assign('data/brand-sets/equipment-ui.json',['material_display',key,'name'],name);
      else if(name&&row.name)assign('data/brand-sets/equipment-ui.json',['material_display',key,'name'],name);
    }
  }
  const attributes=catalogs['data/equipment/attributes.json'];
  if(units?.length&&attributes?.identities){
    const assign=(file,steps,value)=>{const target=cell(catalogs[file],steps,true);if(target.obj[target.key]!==value){target.obj[target.key]=value;changes.push({file,path:steps,derived:true});}};
    for(const [file,collection,rows] of [['data/equipment/attributes.json','core_attributes',attributes.core_attributes],['data/brand-sets/minor-attributes.json','attributes',catalogs['data/brand-sets/minor-attributes.json'].attributes]]){
      for(const row of rows){const identity=attributes.identities[row.id];assert(identity,'Public attribute identity missing');
        for(const field of ['zh_name','en_name','unit_type'])assign(file,[collection,{key:'id',value:row.id},field],field==='zh_name'?identity.display_alias||identity.zh_name:identity[field]);
      }
    }
    for(const rule of attributes.rules.filter(r=>r.kind==='core'))assign('data/brand-sets/equipment-ui.json',['major_names',rule.core_type],attributes.identities[rule.attribute_id].display_alias||attributes.identities[rule.attribute_id].zh_name);
  }
  return {catalogs,hashes,changes};
}
module.exports={files,load,cell,plan};
