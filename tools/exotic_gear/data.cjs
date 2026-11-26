'use strict';
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const attributes=require('../equipment_attributes/catalog.js');
const root=path.resolve(__dirname,'../..');
function blueprintData(catalog){
  const blueprints=catalog.blueprints,blueprint_sources=catalog.blueprint_sources;
  if(!Array.isArray(blueprints)||!Array.isArray(blueprint_sources))throw new Error('BLUEPRINT_CATALOG');
  const plain=s=>typeof s==='string'&&s.trim()===s&&s.length>0&&!/[<>{}\[\]|\x00-\x1f]/.test(s);
  const evidence=e=>Array.isArray(e)&&e.length>0&&e.every(plain);
  const sources=new Set(),ids=new Set();
  for(const s of blueprint_sources){
    if(!/^blueprint_source_[a-f0-9]{32}$/.test(s.id)||sources.has(s.id)||!plain(s.text)||!['native_only','current_confirmed'].includes(s.verification)||!evidence(s.evidence))throw new Error('BLUEPRINT_SOURCE');
    if(s.verification==='current_confirmed'&&!evidence(s.current_evidence))throw new Error('BLUEPRINT_CURRENT_EVIDENCE');
    sources.add(s.id);
  }
  for(const b of blueprints){
    if(!/^blueprint:[a-f0-9]{32}$/.test(b.id)||ids.has(b.id)||!/^exotic:[a-f0-9]{32}$/.test(b.target_id)||!['craft','reconfigure'].includes(b.purpose)||!plain(b.name)||!evidence(b.evidence))throw new Error('BLUEPRINT_IDENTITY');
    if(!Array.isArray(b.source_refs)||new Set(b.source_refs).size!==b.source_refs.length||b.source_refs.some(id=>!sources.has(id)))throw new Error('BLUEPRINT_SOURCE_REFERENCE');
    if(b.kind!==undefined&&(b.purpose!=='craft'||!['retaliation','special'].includes(b.kind)))throw new Error('BLUEPRINT_KIND');
    ids.add(b.id);
  }
  return {blueprints,blueprint_sources};
}
function equipmentData(workspace,records=require('../equipment/database.cjs').load(workspace)){
  const json=p=>require('../identity.cjs').raw(workspace,p);
  const source=json('data/equipment/attributes.json'),minor=json('data/brand-sets/minor-attributes.json'),presets=json('data/brand-sets/fixed-minor-presets.json');
  const shared={base:json('data/brand-sets/equipment-base-rules.json'),ui:json('data/brand-sets/equipment-ui.json')};
  const equipment={};
  for(const [id,entity] of Object.entries(records.entities)){
    if(entity.template!=='奇特装备信息')continue;
    equipment[id]={fields:require('../equipment/projection.cjs').parameters(entity,id),slots:entity.slots};
    if(entity.visuals?.inventory)equipment[id].inventory_asset=entity.visuals.inventory.asset_ref;
  }
  const acquisition=json('data/brand-sets/acquisition-methods.json'),crafting=require('../equipment/crafting.cjs');
  const talents=json('data/exotic-gear/talents.json').talents,seen=new Set();
  for(const t of talents){
    if(!/^exotic_talent_[a-f0-9]{32}$/.test(t.id)||seen.has(t.id))throw new Error('EXOTIC_TALENT_ID');seen.add(t.id);
  }
  return {equipment,attributes:attributes.project(source,minor,presets,shared),talents,...blueprintData(crafting.exotic(crafting.load(workspace),records,acquisition))};
}
function projectReader({equipment,attributes,blueprints}){
  const fields={
    equipment,
    attributes:{
      rules:attributes.rules.map(({id,kind,constant,core_type,display_max,attribute_id,category})=>({id,kind,constant,core_type,display_max,attribute_id,category})),
      pools:attributes.pools.map(({id,kind,rules})=>({id,kind,rules}))
    },
    blueprints:blueprints.map(({id,target_id,purpose,name})=>({id,target_id,purpose,name}))
  };
  const version='equipment-'+crypto.createHash('sha256').update(JSON.stringify(fields)).digest('hex').slice(0,16);
  return {...fields,version};
}
function snapshot(workspace=root,records){
  const data=equipmentData(workspace,records);
  const talents=require('../identity.cjs').read(workspace,'data/exotic-gear/talents.json',data.talents);
  return {...data,talents,version:projectReader(data).version};
}
function lua(v){
  if(v===null||v===undefined)return 'nil';
  if(typeof v==='string')return '"'+v.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/[\x00-\x1f\x7f]/g,c=>'\\'+c.charCodeAt(0).toString().padStart(3,'0'))+'"';
  if(typeof v==='number'||typeof v==='boolean')return String(v);
  return '{'+(Array.isArray(v)?v.map(lua):Object.entries(v).filter(([,x])=>x!==undefined).map(([k,x])=>'['+lua(k)+']='+lua(x))).join(',')+'}';
}
function readerData(workspace=root){
  return 'return '+lua(projectReader(equipmentData(workspace)))+'\n';
}
module.exports={snapshot,readerData,blueprintData};
