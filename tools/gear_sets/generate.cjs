'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const src=path.resolve(root,'ui/editor/src');
const schema={template:'装备组信息',slot_rules:require('../../ui/editor/src/contract.js').slots,collections:{装备资料:{template:'装备组装备',fields:Object.fromEntries(['装备部位','装备名称','英文原名','装备UID','核心属性规则','次属性规则','来源说明'].map(k=>[k,{}]))}}},generator='tools/gear_sets/generate.cjs@v1';
const json=file=>JSON.parse(fs.readFileSync(file,'utf8'));
const hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
function noLinks(target,workspace=root){
  for(let current=target;current!==workspace;current=path.dirname(current)){
    assert(current!==path.dirname(current),'Path outside workspace');
    let stat;try{stat=fs.lstatSync(current);}catch(error){if(error.code!=='ENOENT')throw error;}
    assert(!stat||!stat.isSymbolicLink(),'Symlink path');
  }
}
function sourcePath(source,workspace=root){
  assert(/^wiki\/pages\/gear-sets\/[^/\\]+\.wiki$/.test(source),'Invalid gear set source');
  const target=path.resolve(workspace,source);noLinks(target,workspace);return target;
}
function catalog(){
  const data=require('../identity.cjs').read(root,'data/gear-sets/sets.json');
  assert.equal(data.schema_version,1);assert(Array.isArray(data.sets));
  for(const key of ['id','title','source'])assert.equal(new Set(data.sets.map(r=>r[key])).size,data.sets.length,'Duplicate '+key);
  for(const r of data.sets){
    assert(/^set:[a-z0-9_-]+$/.test(r.id),'Gear set identity required');
    assert(typeof r.title==='string'&&r.title.trim()===r.title&&r.title&&!/[#:\\[\]{}<>|]/.test(r.title),'Invalid title');
    sourcePath(r.source);assert(Array.isArray(r.sources)&&r.sources.length&&r.sources.every(s=>typeof s==='string'&&s.trim()),'Confirmed sources required');
  }
  return data;
}
function value(key){return '{{{'+key+'|}}}';}
function optional(key,body){return '{{#if:'+value(key)+'|'+body+'}}';}
function templates(){
  const result={};
  const identity='|entity='+value('资料ID')+'|effects='+value('效果资料')+'|id='+value('GearSet ID');
  const slots=require(path.join(src,'contract.js')).slots;
  const blueprintRows=Object.entries(slots).map(([slot,label])=>'<dt>{{TD2图标|类别=equipment_slot|键='+slot+'}}'+label+'图纸</dt><dd>{{品牌图纸列表|列表='+value(slot+'图纸')+'}}</dd>').join('');
  const sourceHeading=label=>'<div class="td2-source-heading" role="heading" aria-level="3">'+label+'</div>';
  const dismantleArgs='|装备组='+value('GearSet ID')+'|品牌材料='+value('装备组分解材料')+'|品牌='+value('GearSet ID');
  const dismantleCards=Object.keys(schema.slot_rules).map(slot=>'<div class="td2-equipment-card">{{装备标题卡|章节标题=否|图标键='+slot+'|中文名称='+slots[slot]+'|英文名称='+slot+'|品质=gear_set}}{{TD2分解规则|'+slot+dismantleArgs+'}}</div>').join('');
  const dismantle='{{#switch:{{TD2分解规则|known'+dismantleArgs+'}}|1=<div class="td2-equipment-grid">'+dismantleCards+'</div>|#default={{TD2材料行|名称='+value('装备组分解材料')+'|品牌='+value('GearSet ID')+'|显示数量=否}}}}';
  const blueprintArgs='|source_subject={{{资料ID|}}}';
  const equipmentArgs='|source_subject={{{资料ID|}}}';
  const acquisition='<h2>制作与获取</h2>'+sourceHeading('[[{{TD2页面地址|crafting-guide}}|装备图纸]]')+'<dl class="td2-ordinary-blueprints">'+blueprintRows+'</dl>'
    +'{{#if:{{#invoke:TD2品牌投影|ordinaryBlueprintSource'+blueprintArgs+'}}|<div class="td2-divider-soft" aria-hidden="true"></div>'+sourceHeading('{{#invoke:TD2品牌投影|blueprintHeading'+blueprintArgs+'}}')+'<div class="td2-acquisition-result">{{#invoke:TD2品牌投影|ordinaryBlueprintSource'+blueprintArgs+'}}</div>}}'
    +'<div class="td2-divider-soft" aria-hidden="true"></div>'+sourceHeading('{{#invoke:TD2品牌投影|acquisitionHeading'+equipmentArgs+'}}')+'{{#invoke:TD2品牌投影|acquisition'+equipmentArgs+'}}';
  result[schema.template]='<includeonly><div class="td2-brand td2-gear-set" data-brand="'+value('装备组名称')+'">\n<div class="td2-brand-top">'+optional('英文原名','<div class="td2-brand-name-en" lang="en">'+value('英文原名')+'</div>')+value('简介')+'<div class="td2-brand-bonus-header">{{品牌套装信息框|图标品牌='+value('映射名称')+'|套装全称='+value('装备组名称')+'|品质=gear_set|品质图标=mask}}<h2>套装加成</h2></div>\n<div class="td2-brand-bonuses">'+
    '{{#invoke:TD2装备组投影|effects'+identity+'|heading=none}}</div></div>\n'+
    optional('装备资料','<h2>装备属性</h2><div class="td2-equipment-grid">{{#invoke:TD2装备组投影|equipment'+identity+'|equipment='+value('装备资料')+'}}</div>')+acquisition+'{{#if:'+value('装备组分解材料')+'{{#switch:{{TD2分解规则|known'+dismantleArgs+'}}|1=1|#default=}}|<h2>分解产物</h2>'+dismantle+'}}'+optional('其他机制','<h2>其他资料</h2>'+value('其他机制'))+'\n</div><div class="td2-brand td2-gear-footer">{{TD2普通装备规则|expertise}}{{#invoke:TD2资料记录|references}}<references/></div>{{TD2装备导航}}</includeonly>\n';
  result['装备组内容']=result[schema.template];
  result[schema.template]='<includeonly>{{#invoke:TD2资料映射|render}}</includeonly>\n';
  result[schema.collections['装备资料'].template]='<includeonly>{{#invoke:TD2装备组投影|item'+Object.keys(schema.collections['装备资料'].fields).map(k=>'|'+k+'='+value(k)).join('')+'}}</includeonly>\n';
  return result;
}
function readerModule(){
  return fs.readFileSync(path.join(__dirname,'reader.lua'),'utf8').replace(/\r\n/g,'\n');
}
function main(args){
  const registry=json(path.join(root,'publishing/registry.json'));
  if(args[0]==='templates'||args[0]==='check'){
    const outputs={
      'wiki/modules/TD2装备组投影.lua':readerModule(),
      ...Object.fromEntries(Object.entries(templates()).map(([title,raw])=>['wiki/templates/'+title+'.wiki',raw]))
    };
    const generated=require('../generation.cjs');
    generated.apply(generated.plan(root,outputs,registry,generator),args[0]==='check');
    return;
  }
  throw new Error('Use templates or check');
}
module.exports={catalog,templates,readerModule,hash};
if(require.main===module)main(process.argv.slice(2));
