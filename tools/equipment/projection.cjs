'use strict';
const effects=require('../../ui/editor/src/page-effects.js'),page=require('./page.cjs');
const crafting=require('./crafting.cjs');
function parameters(entity,id){
  const fields={...crafting.fields(entity,id),...entity.fields,映射名称:id};
  if(entity.template==='奇特装备信息')fields.装备ID=id;
  if(entity.template==='装备组信息')fields['GearSet ID']=id;
  for(const [key,collection] of Object.entries(entity.collections||{})){
    if(key==='具名装备资料'||key==='武器型号资料')continue;
    fields[key]=collection.rows.map(row=>page.record(collection.template,row).replace(collection.template+'\n',collection.template)).join('\n');
  }
  fields.效果资料=effects.write(entity.effects.map(row=>({...Object.fromEntries(Object.entries(row).filter(([k])=>!effects.mappedFields.includes(k))),引用:row.引用||id+'#'+row.效果ID}))).replace(/\{\{装备效果\n/g,'{{装备效果');
  for(const rule of entity.rules||[]){
    if(!rule.id.startsWith('slot:'))continue;
    const slot=rule.id.slice(5),core=rule.core;
    fields.部分部位主属性不同='是';fields[slot+'使用不同规则']='是';fields[slot+'允许主核心']=core.types.join(';');
    fields[slot+'主核心槽数']=String(core.count);
    if(slot==='backpack')fields.backpack同时拥有主核心=core.selection==='fixed'&&core.count>1?'是':'否';
    fields[slot+'次属性槽数']=String(rule.minor.count);
    fields[slot+'插件槽数']=String(rule.mods);
  }
  fields.默认允许主核心=(entity.rules?.find(r=>r.id==='slot:mask')?.core.types||[]).join(';');
  return fields;
}
function named(entity){
  return (entity.collections?.具名装备资料?.rows||[]).map(row=>{
    if(row.talent_mode==='fixed'){
      const talents=entity.effects.filter(effect=>effect.所属装备===row.stable_id||effect.效果ID===row.天赋引用);
      if(!row.天赋引用||!talents.length||talents.some(effect=>effect.所属装备!==row.stable_id||effect.效果ID!==row.天赋引用||!effect.名称?.trim()||!effect.描述?.trim()))throw new Error('具名装备天赋效果关联无效: '+row.stable_id+' / '+(row.天赋引用||''));
    }
    const fields={所属品牌:entity.fields.套装全称,...crafting.named(entity,row),...row},rule=entity.rules?.find(r=>r.id==='named:'+row.stable_id);
    if(rule){
      fields.主核心组合=rule.core.selection==='fixed'&&rule.core.count>1?'同时拥有三种主核心':'单核心';
      fields.允许主核心=rule.core.types.join(';');fields.主核心槽数=String(rule.core.count);
      fields.次属性槽例外='是';fields.次属性槽数=String(rule.minor.count);
      fields.插件槽例外='是';fields.插件槽数=String(rule.mods);
      fields.固定次属性=rule.minor.fixed.join(';');
    }
    return fields;
  });
}
function reader(database,options={}){
  const entities={},names={};
  const acquisition=require('./acquisition.cjs'),shared=options.acquisition||acquisition.rules(options.workspace);
  const native=options.crafting||crafting.load(options.workspace);
  const blueprints=crafting.playerBlueprints(native,shared.unavailable_blueprints);
  for(const [id,entity] of Object.entries(database.entities)){
    const rows=named(entity);
    entities[id]={template:entity.template,fields:parameters(entity,id),named:rows.map(r=>r.stable_id),rules:Object.fromEntries((entity.rules||[]).map(r=>[r.id,r]))};
    if(entity.template==='武器信息')entities[id].weapons=require('./weapons.cjs').rows(entity,options.workspace,blueprints);
    for(const row of rows){if(names[row.stable_id])throw new Error('Duplicate named identity');names[row.stable_id]={...row,资料ID:id};}
  }
  return {entities,named:names,acquisition:acquisition.build(native,database,shared)};
}
function editor(database){
  return Object.fromEntries(Object.entries(database.entities).map(([id,e])=>[id,{template:e.template,title:e.fields.套装全称||e.fields.装备组名称||e.fields.装备名称,
    ...(['装备组信息','奇特装备信息','武器信息'].includes(e.template)?{talents:e.effects.filter(r=>r.名称).map(r=>({id:r.效果ID,mode:r.模式,name:r.名称}))}:{})}]));
}
module.exports={parameters,named,reader,editor};
