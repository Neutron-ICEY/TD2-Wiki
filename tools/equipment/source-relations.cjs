'use strict';

function validateConditions(node,names,options={}){
  if(!node)return;
  if(Array.isArray(node)){node.forEach(n=>validateConditions(n,names,options));return;}
  if(!node.type){
    if(Object.keys(node).some(k=>!['group','item'].includes(k)))throw new Error('条件结构尚未解析');
    Object.values(node).forEach(n=>validateConditions(n,names,options));return;
  }
  const props={};
  for(const p of node.properties||[]){const i=p.indexOf(' '),key=p.slice(0,i);if(i<1||Object.hasOwn(props,key))throw new Error('条件参数无效');props[key]=p.slice(i+1);}
  const allowed=new Set(['myIsNegated']),children=node.children||[];
  if(['myConditions','myConditionList','myConditionsA','myConditionsB','ORCondition'].includes(node.type)){
    if(node.type==='ORCondition'&&!children.length)throw new Error('空的或条件');
    children.forEach(n=>validateConditions(n,names,options));
  }else if(node.type==='LootConditionHasItem'){
    allowed.add('myRequiredItemType');const item=names[props.myRequiredItemType];
    if(!item?.name||!item.uid)throw new Error('持有物品尚未解析');
  }else if(['LootConditionLooterLevel','LootConditionOpenWorldProgressionTier'].includes(node.type)){
    const level=node.type==='LootConditionLooterLevel',key=level?'myLevel':'myProgressionTier';
    allowed.add(key);allowed.add('myOperator');
    const operator=props.myOperator||(level?'GreaterThanOrEqual':'Equal');
    const value=level?/^\d+$/.exec(props[key]||''):/^WorldTier([0-5])$/.exec(props[key]||'');
    if(!['Equal','NotEqual','GreaterThan','GreaterThanOrEqual','LessThan','LessThanOrEqual'].includes(operator)||!value)throw new Error('等级条件尚未解析');
  }else if(node.type==='LootConditionIsInDarkZone'){
    allowed.add('myEvaluateType');if(props.myEvaluateType&&props.myEvaluateType!=='FALSE')throw new Error('暗区类型条件尚未解析');
  }else if(node.type==='LootConditionIsMissionDifficulty'&&options.runtime){
    allowed.add('myMissionDifficulty');if(!['Story','Normal','Hard','Challenge','Heroic','Legendary'].includes(props.myMissionDifficulty||'Normal'))throw new Error('难度条件尚未解析');
  }else if(node.type==='LootConditionGlobalDifficulty'&&options.runtime){
    allowed.add('myGlobalDifficulty');allowed.add('myOperator');
    if(!['Normal','Hard','Challenge','Heroic','Legendary'].includes(props.myGlobalDifficulty||'Normal')||(props.myOperator||'Equal')!=='Equal')throw new Error('全局难度条件尚未解析');
  }else throw new Error('条件尚未解析：'+node.type);
  if(children.length&&!['myConditions','myConditionList','myConditionsA','myConditionsB','ORCondition'].includes(node.type))throw new Error('条件包含尚未解析的子项');
  if(Object.keys(props).some(k=>!allowed.has(k)))throw new Error('条件包含尚未解析的参数');
  if(props.myIsNegated&&!['TRUE','FALSE'].includes(props.myIsNegated))throw new Error('条件否定值无效');
}

function owner(data,records,uid){
  const item=data.items[uid],entity=records.entities[item?.entity_id];
  if(!entity)return null;
  if(item.kind!=='named')return item.entity_id;
  if(entity.template==='武器信息'){
    const row=entity.collections?.武器型号资料?.rows.find(r=>r.stable_id===item.record_id)?.data;
    return row&&[row.装备UID,...(row.variants||[]).map(v=>v.uid)].includes(uid)?row.stable_id:null;
  }
  const named=entity.collections?.具名装备资料?.rows.find(r=>r.stable_id===item.record_id);
  return named&&(named.装备UID||named.stable_id.replace(/^gear_/,'')).toUpperCase()===uid?named.stable_id:null;
}

function conditionText(node,names){
  if(!node)return '';
  if(Array.isArray(node)||!node.type)return [...new Set(Object.values(node).map(n=>conditionText(n,names)).filter(Boolean))].join('且');
  const props=Object.fromEntries((node.properties||[]).map(p=>[p.split(' ')[0],p.slice(p.indexOf(' ')+1)]));
  let text='';
  if(node.type==='LootConditionHasItem'){
    const item=names[props.myRequiredItemType];
    text=item.hunterUnlock&&props.myIsNegated!=='TRUE'?'猎人箱解锁后':'持有'+item.name;
  }
  else if(node.type==='LootConditionIsInDarkZone')text='位于暗区';
  else if(['LootConditionLooterLevel','LootConditionOpenWorldProgressionTier'].includes(node.type)){
    const level=node.type==='LootConditionLooterLevel',op=props.myOperator||(level?'GreaterThanOrEqual':'Equal');
    const relation={GreaterThanOrEqual:'达到',GreaterThan:'高于',LessThanOrEqual:'不超过',LessThan:'低于',Equal:'为',NotEqual:'不为'}[op];
    text=level?'等级'+relation+props.myLevel+'级':'世界等级'+relation+props.myProgressionTier.slice(-1);
  }else{
    const children=(node.children||[]).map(n=>conditionText(n,names));
    if(node.type==='ORCondition'&&children.includes(''))return '';
    const terms=[...new Set(children.filter(Boolean))];
    text=terms.join(node.type==='ORCondition'?'或':'且');
  }
  return text&&props.myIsNegated==='TRUE'?'非（'+text+'）':text;
}

function checkCraftConditions(bp,byFile){
  function visit(node){
    if(node.type==='CraftingConditionItem'){
      const raw=(node.properties||[]).find(p=>p.startsWith('myItem '))?.slice(7).replace(/^"|"$/g,'');
      const filename=raw?.startsWith('./')?bp.source.slice(0,bp.source.lastIndexOf('/')+1)+raw.slice(2):raw;
      if(!byFile.has(filename)||node.properties.length!==1||node.children?.length)throw new Error('制作条件尚未核实');
      return byFile.get(filename);
    }
    if(!['myConditions','myAlreadyCraftedConditions'].includes(node.type)||node.properties?.length)throw new Error('制作条件尚未核实');
    for(const child of node.children||[]){
      const item=visit(child);
      if(item&&(node.type!=='myAlreadyCraftedConditions'||!bp.targets.includes(item)))throw new Error('制作所需物品尚未核实');
    }
  }
  for(const condition of bp.conditions||[])visit(condition);
}

function build(data,records){
  const subjects={};
  const byFile=new Map(Object.entries(data.items).map(([uid,i])=>[i.source,uid]));
  const unlocks=data.source_contexts?.hunter_cache?.unlock_items||[];
  const names=Object.fromEntries(Object.entries(data.condition_items||{}).map(([k,v])=>[k,{...v,hunterUnlock:unlocks.includes(v.uid)}]));
  function add(kind,entry,target,route){
    const blueprint=data.blueprints[target],targets=blueprint?blueprint.targets:[target],purpose=blueprint?'blueprint':'equipment';
    for(const subject of new Set(targets.map(uid=>owner(data,records,uid)).filter(Boolean))){
      const row={kind,entry,target,purpose,displayText:route.display_text,restriction:route.restriction||'',origin:route.origin,
        availability:route.availability,pool:route.pool_uid,faction:route.faction,action:route.action,activeTime:route.active_time,confirmable:false,reason:''};
      try{
        const runtime=['common_gear_pool','targeted_slot','targeted_brand','targeted_gearset','targeted_weapon','guardian_drop','pearl_reward','airport_climax_reward','blueprint_reward_pool','summit_challenge_blueprint','dark_zone_npc','equipment_vendor','world_activity','boss_drop','retaliation_blueprint','mission_boss_blueprint'].includes(kind);
        if((route.entry_scope||'route')!=='route'||(runtime||kind==='regular_cache'||kind==='mission_cache_blueprint')&&!route.runtime_witnesses?.length||['direct_reward','project_reward'].includes(kind))throw new Error('获取入口或运行条件尚未闭合');
        const item=blueprint||data.items[target];
        if(!['craft','conversion','specialization_sidearm','specialization_signature'].includes(kind)&&item.obtainable!==true)throw new Error('掉落或售卖资格未确认');
        const weight=(route.definition?.properties||[]).find(p=>p.startsWith('myDropWeight '));
        if(weight&&!(Number.isFinite(Number(weight.slice(13)))&&Number(weight.slice(13))>0))throw new Error('来源权重非正数');
        const conditions=[route.parent_conditions,route.conditions].filter(Boolean);
        if(kind==='craft'||kind==='conversion')checkCraftConditions(data.blueprints[entry],byFile);
        else validateConditions(conditions,names,{runtime});
        if(kind==='vendor'||kind==='exotic_cache'){
          row.conditions=conditions;
          row.requirement=conditionText(conditions,names);
        }
        row.confirmable=true;
      }catch(error){row.reason=error.message;}
      (subjects[subject]??=[]).push(row);
    }
  }
  for(const [kind,routes]of Object.entries(data.routes||{}))for(const route of Object.values(routes)){
    const entry=route.entry_uid||route.project_uid||route.reward_uid;
    if(entry)for(const target of route.targets||[])if(data.items[target]||data.blueprints[target])add(kind,entry,target,route);
  }
  for(const [uid,bp]of Object.entries(data.blueprints)){
    if(bp.purpose==='craft')for(const target of bp.targets)add('craft',uid,target,{});
    if(bp.purpose==='conversion'&&data.items[bp.input_uid]?.name)for(const target of bp.targets){
      add('conversion',uid,target,{display_text:'制作台外观转换（需要'+data.items[bp.input_uid].name+'）'});
    }
  }
  for(const entity of Object.values(records.entities))for(const {data:model} of entity.collections?.武器型号资料?.rows||[]){
    const spec=model.specialization,target=model.装备UID,item=data.items[target];
    if(model.kind==='signature'&&spec?.name&&spec.element_uid&&spec.uid&&item?.slot==='SignatureWeapon'&&item.source===spec.item_source){
      add('specialization_signature',spec.element_uid,target,{display_text:spec.name+'专长解锁'});
    }
  }
  return subjects;
}
module.exports={build,validateConditions,conditionText,owner};
