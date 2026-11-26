'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');let cached;
function load(workspace=root){
  const file=path.join(workspace,'data/equipment/crafting.json');if(!fs.existsSync(file))return null;
  const stat=fs.statSync(file),stamp=file+':'+stat.mtimeMs+':'+stat.size;
  if(cached?.stamp!==stamp)cached={stamp,data:JSON.parse(fs.readFileSync(file,'utf8'))};return cached.data;
}
function playerBlueprints(data,exclusions={}){
  const blueprints={...data?.blueprints};
  for(const [uid,observation] of Object.entries(exclusions)){
    const targets=blueprints[uid]?.targets;
    if(targets?.length!==1||targets[0]!==observation.target||!observation.evidence?.trim())throw new Error('Invalid unavailable blueprint: '+uid);
    delete blueprints[uid];
  }
  return blueprints;
}
function validate(data){
  assert.equal(data.schema_version,1);const uid=/^[A-F0-9]{32}$/;
  for(const [id,item] of Object.entries(data.items||{})){assert(uid.test(id)&&typeof item.entity_id==='string','Invalid native item');assert(['brand','named','gear_set','exotic','weapon'].includes(item.kind));}
  for(const [id,b] of Object.entries(data.blueprints||{})){
    assert(uid.test(id)&&Array.isArray(b.targets)&&b.targets.length>0&&new Set(b.targets).size===b.targets.length,'Invalid blueprint targets');
    assert(b.targets.every(t=>data.items[t]),'Unresolved blueprint target');assert(typeof b.random==='boolean'&&(b.random||b.targets.length===1),'Invalid crafting mode');
    assert(['craft','reconfigure','conversion'].includes(b.purpose));
    if(b.purpose==='conversion')assert(data.items[b.input_uid]&&!b.targets.includes(b.input_uid),'Unresolved conversion input');
    assert((b.source_refs||[]).every(id=>data.sources[id]),'Unresolved source hint');
  }
  return data;
}
function itemName(data,uid,records){
  const item=data.items[uid],entity=records.entities[item.entity_id];if(!entity)return item.name||'';
  if(item.kind==='exotic')return entity.fields.装备名称;
  const row=entity.collections?.[item.collection]?.rows.find(r=>(r.stable_id||r.装备UID)===item.record_id);
  return row?.data?.装备名称||row?.装备名称||row?.中文名称||item.name||'';
}
function name(data,b,records){return b.name||(!b.random&&itemName(data,b.targets[0],records))||'';}
function fields(entity,id,data=load()){
  if(!data)return {};const result={},records={entities:{[id]:entity}};
  const blueprints=Object.entries(data.blueprints||{}).filter(([,b])=>!b.random&&b.targets.some(uid=>data.items[uid]?.entity_id===id));
  if(entity.template==='奇特装备信息'){
    for(const [field,purpose] of [['制作图纸','craft'],['重新配置图纸','reconfigure']]){
      const rows=blueprints.filter(([,b])=>b.purpose===purpose);if(rows.length)result[field]=rows.map(([uid])=>'blueprint:'+uid.toLowerCase()).join(';');
    }
  }else for(const slot of ['mask','backpack','chest','gloves','holster','kneepads']){
    const rows=blueprints.filter(([,b])=>b.purpose==='craft'&&b.targets.some(uid=>data.items[uid]?.slot===slot&&data.items[uid]?.kind!=='named'));
    if(rows.length)result[slot+'图纸']=[...new Set(rows.map(([,b])=>name(data,b,records)).filter(Boolean))].join(';');
  }
  const currency=data.materials?.[id]?.currency_uid,material=data.currencies?.[currency]?.name;
  if(material)result[entity.template==='装备组信息'?'装备组分解材料':'品牌分解材料']=material;
  return result;
}
function named(entity,row,data=load()){
  if(!data)return {};const uid=(row.装备UID||row.stable_id?.replace(/^gear_/,''))?.toUpperCase();
  if(!data.items[uid])return {};
  const rows=Object.values(data.blueprints).filter(b=>!b.random&&b.purpose==='craft'&&b.targets.includes(uid));
  if(!rows.length)return {};
  return {具名图纸名称:[...new Set(rows.map(b=>b.name||row.装备名称))].join(';')};
}
function exotic(data,records,acquisition){
  if(!data)return {blueprints:acquisition.blueprints,blueprint_sources:acquisition.blueprint_sources};
  const rows=Object.entries(data.blueprints).filter(([,b])=>!b.random&&b.targets.length===1&&data.items[b.targets[0]]?.kind==='exotic'&&records.entities[data.items[b.targets[0]].entity_id]?.template==='奇特装备信息');
  return {blueprints:rows.map(([uid,b])=>({id:'blueprint:'+uid.toLowerCase(),target_id:data.items[b.targets[0]].entity_id,purpose:b.purpose,
    name:name(data,b,records),name_origin:b.name?'blueprint_localization':'crafted_item_localization',source_refs:b.source_refs,
    evidence:[b.source],...(b.kind?{kind:b.kind}:{})})),
    blueprint_sources:Object.entries(data.sources).map(([id,s])=>({id,text:s.text,verification:s.verification||'native_only',evidence:[s.source],...(s.current_evidence?{current_evidence:s.current_evidence}:{})}))};
}
module.exports={load,playerBlueprints,validate,fields,named,exotic,itemName};
