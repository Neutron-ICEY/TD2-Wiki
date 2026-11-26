'use strict';
const fs=require('node:fs'),path=require('node:path');
const effects=require('../../ui/editor/src/page-effects.js');
const manual=require('../../ui/editor/src/page-fields.js');
const file='data/equipment/records.json';
function load(root=path.resolve(__dirname,'../..'),snapshot){
  const data=require('../identity.cjs').read(root,file,snapshot);
  if(data.schema_version!==1||!data.entities)throw new Error('Equipment database schema');
  for(const entity of Object.values(data.entities))effects.write(entity.effects);
  return data;
}
function owned(entity,target){
  const steps=target.records||[];
  if(!steps.length)return !manual.isManual(target.field)&&target.field!=='资料ID';
  return steps.length===1;
}
function cell(entity,target,create=false){
  const steps=target.records||[];if(!steps.length)return entity.fields;
  const step=steps[0];let rows;
  if(step.field==='效果资料')rows=entity.effects;
  else if(step.field==='属性槽')rows=entity.slots;
  else if(step.field==='属性配置'){
    if(create)entity.rules??=[];rows=entity.rules||[];
  }else{
    if(create)(entity.collections??={})[step.field]??={template:step.template,rows:[]};
    rows=entity.collections?.[step.field]?.rows||[];
  }
  let row=rows.find(r=>Object.entries(step.id).every(([k,v])=>r[k]===v));
  if(!row&&create){row={...step.id};rows.push(row);}return row;
}
function references(database){
  return Object.entries(database.entities).flatMap(([id,entity])=>[...new Set(entity.effects.map(r=>r.效果ID))].map(effectId=>{
    const rows=entity.effects.filter(r=>r.效果ID===effectId),row=rows[0];
    return {id:id+'#'+effectId,entity:id,pageName:entity.page_title||require('../identity.cjs').display(entity),effectId,
      family:entity.template==='奇特装备信息'?'exotic':entity.template==='装备组信息'?'gear':effectId.startsWith('brand_bonus_')?'bonus':'named',
      label:row.名称||row.属性||'',modes:Object.fromEntries(rows.map(r=>[r.模式,Object.fromEntries(effects.mappedFields.filter(k=>r[k]!==undefined).map(k=>[k,r[k]]))]))};
  }));
}
function value(entity,target){const row=cell(entity,target);return target.records?.[0]?.field==='属性配置'&&target.field==='minor_count'?row?.minor?.count:row?.[target.field];}
function write(entity,target,value){
  const row=cell(entity,target,true);
  if(target.records?.[0]?.field==='武器型号资料'&&target.field==='data')value=JSON.parse(value);
  if(target.records?.[0]?.field==='属性配置'){
    value=JSON.parse(value);if(target.field==='minor_count'){(row.minor??={fixed:[]}).count=value;return;}
  }
  row[target.field]=value;
}
module.exports={file,load,owned,cell,references,value,write};
