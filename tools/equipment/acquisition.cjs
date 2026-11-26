'use strict';
const fs=require('node:fs'),path=require('node:path'),crafting=require('./crafting.cjs'),sources=require('./source-relations.cjs');
const root=path.resolve(__dirname,'../..');
const categories={equipment:{drop:'战利品掉落',activity:'开放世界活动',event:'活动获取',cache:'贮藏箱',craft:'制作台',vendor:'商人',mission:'任务与行动',project:'计划',specialization:'专长',entitlement:'组合包',special:'特殊途径'},
  blueprint:{cache:'贮藏箱',vendor:'商人',project:'计划',specialization:'专长',reward:'任务与挑战奖励',entitlement:'组合包',special:'特殊途径'}};
const purposeNames={craft:'制作图纸',reconfigure:'重新配置图纸',conversion:'外观转换图纸'};
const retaliationActions={kill_squad:'击杀杀戮小队有几率获得',defend_territory:'成功保卫领土有几率获得'};
const targetedDrops=new Set(['targeted_weapon','targeted_slot','targeted_gearset','targeted_brand']);
const terminalUid='373FA64D6A9AEF28000BD9DC3959515F';
const blueprintOrder=['完成计划','完成高峰大厦挑战','接管警戒等级3以上的控制点','依娜亚出售'];
const cacheOrder=['具名贮藏箱','奇特贮藏箱','暗区精通贮藏箱','实战精通贮藏箱','冲突战贮藏箱','冲突战专家贮藏箱'];

function sourceText(rule,fallback=''){
  if(!rule.preset)return rule.text||fallback;
  const filled=(...values)=>values.every(v=>typeof v==='string'&&v.trim());
  if(rule.text!==undefined)throw new Error('ACQUISITION_PRESET: use preset fields instead of text');
  if(rule.preset==='manhunt'&&filled(rule.mission,rule.condition)){
    if(rule.condition.trim()==='大师难度必定获得')throw new Error('ACQUISITION_PRESET: confirmed first-clear rewards must use 首次通关大师难度必定获得');
    return rule.mission+' - '+rule.condition;
  }
  if(rule.preset==='retaliation'&&filled(rule.faction)&&Object.hasOwn(retaliationActions,rule.action))return retaliationActions[rule.action]+' [报复行动：'+rule.faction+']';
  throw new Error('ACQUISITION_PRESET: unknown preset or missing fields');
}

function availability(rule,row,data){
  if(rule.availability==='legacy_manhunt')return data.source_contexts?.legacy_manhunts?.[rule.climax_uid]?'permanent':'unconfirmed_unlock';
  if(rule.availability==='cache_supply'){
    const supply=data.source_contexts?.cache_supply?.[row.entry]||[];
    if(supply.some(s=>(s.vendor||s.xp)&&!s.availability))return 'recurring';
    if(supply.some(s=>s.availability==='season_slot'))return 'limited';
    return data.source_contexts?.cache_windows?.[row.entry]?.length?'limited':'unconfirmed_supply';
  }
  if(rule.availability==='origin')return row.origin&&row.availability||'unresolved';
  if(rule.availability==='origin_pool')return row.pool?'recurring':'unresolved';
  return rule.availability||'unresolved';
}
function current(status){return ['permanent','recurring','entitlement'].includes(status);}

function pastRecipeGrant(row,reviewDate){
  if(!['season_blueprint','journey_blueprint'].includes(row.kind)||!/^\d{4}-\d\d-\d\d$/u.test(reviewDate||''))return false;
  const window=/^"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) to (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)"$/u.exec(row.activeTime||'');
  if(!window)return false;
  const start=Date.parse(window[1].replace(' ','T')+'Z'),end=Date.parse(window[2].replace(' ','T')+'Z');
  return start<=Date.parse(reviewDate+'T00:00:00Z')&&start<=end;
}

// Only simplify positive AND branches. Negation and OR retain the native
// requirement as a whole, so dropping a default level cannot change its meaning.
function readerCondition(row,names){
  const leaves=[];
  function collect(node){
    if(!node)return true;
    if(Array.isArray(node)||!node.type)return Object.values(node).every(collect);
    if(node.properties?.includes('myIsNegated TRUE')||node.type==='ORCondition')return false;
    if(['myConditions','myConditionList','myConditionsA','myConditionsB'].includes(node.type))return (node.children||[]).every(collect);
    leaves.push(node);
    return true;
  }
  if(!row.conditions||!collect(row.conditions))return {text:row.requirement||''};
  const kept=leaves.filter(node=>{
    const p=node.properties||[];
    if(node.type==='LootConditionLooterLevel'&&p.includes('myLevel 40'))
      return p.some(v=>v.startsWith('myOperator ')&&v!=='myOperator GreaterThanOrEqual');
    return !(node.type==='LootConditionOpenWorldProgressionTier'&&p.includes('myProgressionTier WorldTier1')&&p.includes('myOperator GreaterThanOrEqual'));
  });
  const text=sources.conditionText(kept,names);
  if(kept.length===1&&kept[0].type==='LootConditionHasItem'){
    const key=kept[0].properties.find(v=>v.startsWith('myRequiredItemType ')).slice('myRequiredItemType '.length);
    const held=names[key];
    if(!held.hunterUnlock)return {text,held:held.uid,name:held.name};
  }
  return {text};
}

function qualified(base,condition){
  if(!condition)return base;
  if(condition==='猎人箱解锁后'&&base==='依娜亚出售')return condition+base;
  return base+' ['+condition+']';
}

function routeLabel(row,rule){
  if(targetedDrops.has(row.kind)&&row.restriction==='dark_zone')return '暗区战利品掉落';
  if(row.kind==='equipment_vendor'&&row.entry!==terminalUid)return '商人轮换出售';
  if(rule.preset==='retaliation')return sourceText({...rule,faction:row.faction,action:row.action});
  const value=rule.use_route_text?row.displayText:sourceText(rule);
  if(!value)return '';
  switch(row.kind){
    case 'equipment_vendor':return value.replace('（原型）',' [原型]');
    case 'specialization_sidearm':return value.replace(/（40\s*级）$/u,'');
    case 'field_research_blueprint':
    case 'conversion':return value.replace(/（([^（）]+)）$/u,' [$1]');
    default:return value;
  }
}

// Alternatives may be combined only for one entry awarding the very same UID.
function visibleRoutes(routes,outputs){
  const visible=[],entries=new Map();
  for(const row of routes){
    if(!row.condition){visible.push(row);continue;}
    const key=row.kind+'|'+row.entry;
    if(!entries.has(key))entries.set(key,[]);
    entries.get(key).push(row);
  }
  for(const rows of entries.values()){
    const unconditional=rows.find(r=>!r.condition.text);
    if(unconditional){visible.push(unconditional);continue;}
    const held=rows.filter(r=>r.condition.held);
    visible.push(...rows.filter(r=>!r.condition.held));
    if(held.length){
      held.sort((a,b)=>Number(outputs.includes(b.condition.held))-Number(outputs.includes(a.condition.held))
        ||a.condition.name.localeCompare(b.condition.name,'zh-Hans'));
      const names=[...new Set(held.map(r=>r.condition.name))];
      visible.push({...held[0],text:qualified(held[0].base,'持有'+names.join('或'))});
    }
  }
  return visible;
}

function rank(row,purpose){
  if(purpose==='blueprint'){
    const common=blueprintOrder.indexOf(row.text);
    return common<0?10:common;
  }
  if(row.kind==='hunter_cache')return 43;
  if(row.kind==='hunter_vendor')return 44;
  switch(row.category){
    case 'drop':return row.text==='暗区战利品掉落'?1:0;
    case 'event':case 'activity':return 10;
    case 'mission':return 20;
    case 'cache':{
      if(row.kind==='raid_cache')return 39;
      const index=cacheOrder.indexOf(row.base||row.text);
      return 30+(index<0?7:index);
    }
    case 'craft':return 50;
    case 'vendor':return row.entry===terminalUid?61:60;
    default:return 40;
  }
}

function readerMethods(routes,purpose){
  const unique=new Map();
  routes.sort((a,b)=>rank(a,purpose)-rank(b,purpose)||a.text.localeCompare(b.text,'zh-Hans')||a.category.localeCompare(b.category));
  for(const {category,text} of routes)if(!unique.has(text))unique.set(text,{category,text});
  return [...unique.values()];
}

function resolve(data,records,catalog,relations){
  data={...data,blueprints:crafting.playerBlueprints(data,catalog.unavailable_blueprints)};
  relations??=sources.build(data,records);
  const confirmed=catalog.confirmed_equipment_sources||{},awards=catalog.confirmed_blueprint_sources||{};
  const hunterItems=data.source_contexts?.hunter_cache?.unlock_items||[];
  const names=Object.fromEntries(Object.entries(data.condition_items||{}).map(([key,item])=>[key,{...item,hunterUnlock:hunterItems.includes(item.uid)}]));
  const issuedRecipes=new Set();
  for(const [uid,observation] of Object.entries(awards)){
    if(!data.blueprints[uid]||!categories.blueprint[observation.category]||!observation.text?.trim()||!observation.evidence?.length||observation.evidence.some(e=>!e.trim()))throw new Error('BLUEPRINT_REWARD_EVIDENCE');
    if(observation.usable_if_owned===true){
      if(data.blueprints[uid].purpose!=='craft'||data.blueprints[uid].obtainable!==true)throw new Error('BLUEPRINT_CRAFT_EVIDENCE');
      issuedRecipes.add(uid);
    }
  }
  for(const [uid,observation] of Object.entries(confirmed)){
    if(!sources.owner(data,records,uid)||observation.verification!=='current_confirmed'||!observation.evidence?.length||
       observation.evidence.some(e=>typeof e!=='string'||!e.trim())||!sourceText(observation)?.trim()||!categories.equipment[observation.category]||
       observation.entry_uid!==undefined&&!/^[A-F0-9]{32}$/.test(observation.entry_uid))throw new Error('EQUIPMENT_CURRENT_EVIDENCE');
  }
  const owned={},byTarget={},excluded={},facts={};
  for(const id of Object.keys(records.entities))owned[id]=[];
  for(const uid of Object.keys(data.items)){
    const id=sources.owner(data,records,uid);
    if(id)(owned[id]??=[]).push(uid);
  }
  function record(index,uid,row){
    const rows=index[uid]??=[];
    if(!rows.some(r=>r.kind===row.kind&&r.entry===row.entry&&r.text===row.text&&r.status===row.status))rows.push(row);
  }
  const reject=(target,kind,entry,status)=>record(excluded,target,{kind,entry,status});
  const accept=(target,kind,entry,category,text,extra={})=>{
    if(!categories[data.blueprints[target]?'blueprint':'equipment'][category]||!text?.trim())throw new Error('Invalid acquisition method: '+kind);
    record(byTarget,target,{kind,entry,category,text,...extra});
  };
  for(const [target,observation] of [...Object.entries(confirmed),...Object.entries(awards)]){
    const status=availability(observation,{},data);
    if(!current(status)){reject(target,'observation',observation.entry_uid,status);continue;}
    for(const method of observation.methods||[observation])accept(target,'observation',observation.entry_uid,method.category,sourceText(method));
  }
  // A recipe may produce several registered items. Resolve its grants once
  // before assessing crafting for any of those targets.
  const allRows=Object.values(relations).flat();
  for(const [uid,bp] of Object.entries(data.blueprints))for(const ref of bp.source_refs||[]){
    const source=data.sources[ref],rule=catalog.blueprint_source_rules[ref];
    if(!rule||source?.verification!=='current_confirmed'||bp.obtainable!==true)continue;
    if(!source.current_evidence?.length)throw new Error('BLUEPRINT_CURRENT_EVIDENCE');
    if(rule.preset)sourceText(rule);
    const required=rule.preset==='retaliation'?'retaliation_blueprint':rule.requires_route;
    const supported=allRows.some(r=>r.target===uid&&r.kind===required&&r.confirmable&&
      (rule.preset!=='retaliation'||r.faction===rule.faction&&r.action===rule.action));
    if(!supported)reject(uid,'source_info',ref,'unverified_reward_target');
  }
  for(const row of allRows){
    if(['craft','conversion'].includes(row.kind))continue;
    const rule=catalog.native_route_rules[row.kind];
    if(row.purpose==='blueprint'&&!data.blueprints[row.target])continue;
    if(!rule||rule.purpose!==row.purpose||rule.entry_uid!==null&&rule.entry_uid!==row.entry||!row.confirmable){
      reject(row.target,row.kind,row.entry,row.reason||'unresolved');continue;
    }
    const status=availability(rule,row,data);
    if(!current(status)){
      if(status==='limited'&&row.purpose==='blueprint'&&pastRecipeGrant(row,catalog.recipe_grants_verified_through))issuedRecipes.add(row.target);
      reject(row.target,row.kind,row.entry,status);continue;
    }
    const observation=(row.purpose==='blueprint'?awards:confirmed)[row.target];
    if(observation?.entry_uid===row.entry&&current(availability(observation,{},data)))continue;
    const base=routeLabel(row,rule);
    if(!base)continue;
    const condition=row.kind==='vendor'||row.kind==='exotic_cache'?readerCondition(row,names):null;
    accept(row.target,row.kind,row.entry,rule.category,qualified(base,condition?.text),{
      ...(condition&&{condition,base}),...(row.pool&&{pool:row.pool}),...(row.restriction&&{restriction:row.restriction})});
  }
  for(const row of allRows.filter(r=>r.kind==='craft'||r.kind==='conversion')){
    const bp=data.blueprints[row.entry],rule=catalog.native_route_rules[row.kind];
    if(!bp||!rule)continue;
    if(!row.confirmable||bp.obtainable!==true||!current(availability(rule,row,data))||!(byTarget[row.entry]?.length||issuedRecipes.has(row.entry))){
      reject(row.target,row.kind,row.entry,row.reason||'no_confirmed_recipe_access');continue;
    }
    accept(row.target,row.kind,row.entry,rule.category,routeLabel(row,rule));
  }
  for(const [id,uids] of Object.entries(owned)){
    const itemSet=new Set(uids);
    const fact=facts[id]={equipment:[],blueprint:[],hasBlueprint:false};
    fact.equipment=readerMethods(uids.flatMap(uid=>visibleRoutes(byTarget[uid]||[],[uid])),'equipment');
    if(records.entities[id]?.collections?.武器型号资料?.rows.some(({data:model})=>model.kind==='signature'&&itemSet.has(model.装备UID)))continue;
    const blueprints=Object.entries(data.blueprints).filter(([,b])=>b.targets.some(t=>itemSet.has(t)));
    fact.hasBlueprint=blueprints.length>0;
    const exotic=uids.some(uid=>data.items[uid].kind==='exotic');
    const groups=Object.entries(purposeNames).filter(([purpose])=>blueprints.some(([,bp])=>bp.purpose===purpose));
    if(exotic&&groups.length)fact.blueprintGroups=[];
    for(const [purpose,title] of groups){
      const routes=blueprints.filter(([,bp])=>bp.purpose===purpose)
        .flatMap(([uid,bp])=>visibleRoutes(byTarget[uid]||[],bp.targets));
      const methods=readerMethods(routes,'blueprint');
      if(exotic)fact.blueprintGroups.push({title,methods:methods.length?methods.map(r=>r.text):['暂无获取资料']});
      for(const method of methods){
        const text=exotic&&groups.length>1?title+' · '+method.text:method.text;
        if(!fact.blueprint.some(r=>r.text===text))fact.blueprint.push({category:method.category,text});
      }
    }
  }
  return {facts,byTarget,excluded};
}
function build(data,records,catalog,relations){return resolve(data,records,catalog,relations).facts;}
function rules(workspace=root){
  return JSON.parse(fs.readFileSync(path.join(workspace,'data/brand-sets/acquisition-methods.json'),'utf8'));
}
function load(workspace=root,records=require('./database.cjs').load(workspace)){
  return build(crafting.load(workspace),records,rules(workspace));
}
module.exports={categories,build,resolve,load,rules};
