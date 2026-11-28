'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const merge=require('./merge.cjs'),page=require('./page.cjs');
const generation=require('../generation.cjs');
const projectRoot=path.resolve(__dirname,'../..');
const database=require('./database.cjs');
const catalogs=require('./catalog-import.cjs');
const weapons=require('./weapon-import.cjs');
const {talentKey}=require('../../ui/editor/src/page-fields.js');
const hash=text=>text===null?null:require('node:crypto').createHash('sha256').update(text).digest('hex');
const json=value=>JSON.stringify(value,null,2)+'\n';
function reviewedJson(value,before){
  return before!==null&&require('node:util').isDeepStrictEqual(value,JSON.parse(before))?before:json(value);
}
const pythonProbe='import hashlib,json,sys;sys.exit(1) if not (sys.version_info>=(3,11) and hasattr(hashlib,"file_digest")) else print(json.dumps({"td2_python":sys.executable}))';
function probePython(command,args=[],env=process.env){
  const check=require('node:child_process').spawnSync(command,[...args,'-B','-c',pythonProbe],{encoding:'utf8',env,stdio:['ignore','pipe','ignore']});
  if(check.error||check.status!==0)return null;
  const line=(check.stdout||'').trim().split(/\r?\n/).pop();
  if(!line)return null;
  try{
    const parsed=JSON.parse(line);
    const resolved=typeof parsed?.td2_python==='string'?parsed.td2_python.trim():'';
    return resolved&&path.isAbsolute(resolved)&&fs.existsSync(resolved)?resolved:null;
  }catch{return null;}
}
function resolvePython(root=projectRoot,env=process.env,probe=probePython){
  const rel=process.platform==='win32'?'Scripts/python.exe':'bin/python';
  const explicit=env.TD2_PYTHON&&env.TD2_PYTHON.trim();
  if(explicit){
    const command=/[\\/]/.test(explicit)?path.resolve(explicit):explicit;
    const hit=probe(command,[],env);
    if(hit===true)return {command,args:[]};
    if(typeof hit==='string'&&path.isAbsolute(hit))return {command:hit,args:[]};
    throw new Error('TD2_PYTHON is not a usable Python 3.11+ interpreter: '+explicit);
  }
  const candidates=[];
  if(env.VIRTUAL_ENV)candidates.push({command:path.resolve(env.VIRTUAL_ENV,rel),args:[],checkFile:true});
  for(const dir of [...new Set([path.resolve(root),projectRoot])]){
    candidates.push({command:path.join(dir,'.venv',rel),args:[],checkFile:true});
  }
  if(process.platform==='win32')candidates.push({command:'py',args:['-3']},{command:'py',args:[]},{command:'python3',args:[]},{command:'python',args:[]});
  else candidates.push({command:'python3',args:[]},{command:'python',args:[]});
  for(const candidate of candidates){
    if(candidate.checkFile&&!fs.existsSync(candidate.command))continue;
    const hit=probe(candidate.command,candidate.args,env);
    if(hit===true)return {command:candidate.command,args:candidate.args};
    if(typeof hit==='string'&&path.isAbsolute(hit))return {command:hit,args:[]};
  }
  throw new Error('Python 3.11+ interpreter not found for equipment import transaction. Activate .venv or set TD2_PYTHON.');
}
function install(root,request,python=resolvePython(root,process.env)){
  const result=require('node:child_process').spawnSync(python.command,[...python.args,'-B','-X','utf8',path.join(__dirname,'import_transaction.py')],{cwd:root,encoding:'utf8',input:JSON.stringify(request)});
  if(result.error)throw result.error;
  if(result.status!==0)throw new Error(result.stderr.trim()||'Import interrupted ('+(result.signal||result.status)+')');
  return JSON.parse(result.stdout);
}
function plan(input,baseline,read,records=database.load(),currentCatalogs=catalogs.load(projectRoot)){
  assert.equal(input.schema_version,1);assert(Array.isArray(input.entities));
  const next=structuredClone(baseline||{schema_version:1,projection_version:1,entities:{}}),db=structuredClone(records),seen=new Set(),sources=new Set(),changes=[],unavailable=[...(input.unavailable||[])];
  assert.equal(next.schema_version,1);assert([1,2].includes(next.projection_version),'Unsupported native baseline projection version');
  for(const entity of input.entities){
    assert(!seen.has(entity.id),'Duplicate entity');seen.add(entity.id);
    assert(/^wiki\/pages\/(brands|gear-sets|exotic-gear|equipment|weapons)\/[^/\\]+\.wiki$/.test(entity.source),'Invalid page source');
    assert(!sources.has(entity.source.toLowerCase()),'Duplicate page source');sources.add(entity.source.toLowerCase());
    const existing=read(entity.source),raw=existing??'{{'+entity.template+'\n|资料ID='+entity.id+'\n}}',currentPage=page.read(raw);
    assert.equal(currentPage.root.template,entity.template);assert.equal(currentPage.root.fields.资料ID?.value,entity.id,'Page identity mismatch');
    const previous=next.entities[entity.id];assert(!previous?.source||previous.source===entity.source,'Reconcile imported page identity before writing');
    const record=db.entities[entity.id]??={source:entity.source,template:entity.template,fields:{},effects:[],slots:[],collections:{}};
    assert.equal(record.source,entity.source);const units={...(previous?.units||{})},pageUnits=[],fields=[],targets=new Set();
    const models={...previous?.weaponModels},notes=new Set(previous?.orphanNotes||[]),modelResults=[];
    for(const unit of entity.units){
      const key=merge.key(unit.target);assert(!targets.has(key),'Duplicate native target');targets.add(key);
      assert(typeof unit.value==='string'&&unit.semantic!==undefined,'Incomplete native unit');
      if(weapons.isModel(unit.target)){
        assert.equal(entity.template,'武器信息');
        const model=weapons.model(record,unit,units,models,unavailable);
        modelResults.push(model);fields.push(...model.fields);
      }
    }
    const weaponEffect=unit=>entity.template==='武器信息'&&unit.target.records?.[0]?.field==='效果资料';
    const permitted=weapons.effects(record,modelResults,entity.units.filter(weaponEffect),units,notes,fields);
    for(const unit of entity.units){
      if(weapons.isModel(unit.target))continue;
      if(weaponEffect(unit)){
        const {效果ID:id,模式:mode}=unit.target.records[0].id;
        if(!permitted.has(talentKey(id,mode)))continue;
      }
      const key=merge.key(unit.target);
      if(!database.owned(record,unit.target)){pageUnits.push(unit);continue;}
      const digest=merge.fingerprint(unit.semantic),current=database.value(record,unit.target),changed=(!existing||current===undefined||previous&&units[key]!==undefined)&&units[key]!==digest;
      if(changed){
        if((typeof current==='object'?JSON.stringify(current):String(current))!==unit.value){database.write(record,unit.target,unit.value);fields.push(unit.target);}
      }
      units[key]=digest;
    }
    const result=merge.merge(raw,existing===null?{units:{}}:previous,{schema_version:1,units:pageUnits});
    for(const unit of pageUnits){const key=merge.key(unit.target);units[key]=result.baseline.units[key];}
    next.entities[entity.id]={units};
    if(Object.keys(models).length){
      next.entities[entity.id].weaponModels=models;
      next.projection_version=2;
    }
    const orphanNotes=[...notes].filter(name=>Object.hasOwn(currentPage.root.fields,name));
    if(orphanNotes.length)next.entities[entity.id].orphanNotes=orphanNotes;
    changes.push({id:entity.id,source:entity.source,before:existing,raw:result.raw,fields:[...fields,...result.changes],initialized:!previous,...(orphanNotes.length?{orphanNotes}:{})});
  }
  const shared=catalogs.plan(input.catalogs,next.catalogs,currentCatalogs);
  if(shared.catalogs['data/equipment/crafting.json'])require('./crafting.cjs').validate(shared.catalogs['data/equipment/crafting.json']);
  if(input.catalogs){
    const acquisition=shared.catalogs['data/brand-sets/acquisition-methods.json'],exotic=require('../exotic_gear/data.cjs');
    exotic.blueprintData(require('./crafting.cjs').exotic(shared.catalogs['data/equipment/crafting.json'],db,acquisition));
  }
  if(input.catalogs)next.catalogs=shared.hashes;
  return {baseline:next,database:db,pages:changes,catalogs:shared.catalogs,catalogChanges:shared.changes,unavailable};
}
function validatePage(row,inputs){
  const local=require('../../ui/editor/src/local-session.js');
  const session=local.create(row.raw,inputs.catalog,inputs.options);
  if(!session.blockers.length){session.serialize();return;}
  const allowed=new Set((row.orphanNotes||[]).map(name=>'equipment/'+name));
  assert(session.blockers.every(b=>b.code==='UNKNOWN_PARAMETER'&&allowed.has(b.path)),'Invalid imported structure: '+row.source);
  // Reopen the remaining parameters normally. The archived note is never stripped from the output.
  local.create(page.remove(row.raw,row.orphanNotes),inputs.catalog,inputs.options).serialize();
}
function reviewNames(pages,registry){
  const names=new Set();
  return new Map(pages.map(row=>{
    const entries=registry.entries.filter(e=>e.source===row.source),entry=entries[0];
    assert(entries.length===1&&entry.related_entity===row.id&&entry.kind==='pages'&&entry.namespace===0&&entry.ownership==='generated'&&entry.generator==='tools/equipment/import.cjs@v1','Register the page with the equipment importer before importing: '+row.source);
    assert(/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(entry.id),'Invalid registration ID');
    const filename=entry.id+'.wiki',key=require('../naming.cjs').normalized(filename);
    require('../naming.cjs').safeRelative(filename);
    assert(!names.has(key),'Duplicate review filename');names.add(key);
    return [row.source,filename];
  }));
}
function main(args,root=projectRoot){
  const inputFile=args[0],output=args[1];assert(inputFile&&output,'Usage: node tools/equipment/import.cjs projection.json fresh-output [--write] [--baseline path]');
  const outputPath=path.resolve(output);assert(outputPath.startsWith(path.join(root,'dist')+path.sep),'Use a fresh dist directory');
  generation.targetPath(root,path.relative(root,path.join(outputPath,'result.json')).split(path.sep).join('/'));
  const at=args.indexOf('--baseline'),baselineFile=path.resolve(at<0?path.join(root,'data/equipment/native-baseline.json'):args[at+1]);
  assert(baselineFile.startsWith(root+path.sep),'Baseline outside workspace');
  generation.targetPath(root,path.relative(root,baselineFile).split(path.sep).join('/'));
  const projection=fs.readFileSync(inputFile,'utf8'),input=JSON.parse(projection);
  const registry=JSON.parse(fs.readFileSync(path.join(root,'publishing/registry.json'),'utf8'));
  const filenames=reviewNames(input.entities,registry);
  const baselineSource=path.relative(root,baselineFile).split(path.sep).join('/');
  const request={identity:hash(JSON.stringify([hash(projection),baselineSource,args.includes('--initialize')])),baseline:baselineSource,
    targets:[...filenames.keys(),database.file,...catalogs.files,baselineSource]};
  assert.equal(new Set(request.targets.map(s=>s.toLowerCase())).size,request.targets.length,'Duplicate import target');
  const writeMode=args.includes('--write');
  const python=writeMode?resolvePython(root,process.env):null;
  if(writeMode&&fs.existsSync(path.join(root,'.cache/equipment-import/pending.json'))){
    const resumed=install(root,request,python);
    if(resumed){console.log('Completed pending import: dist/'+resumed);return;}
  }
  assert(!fs.existsSync(outputPath),'Use a fresh dist directory');
  const beforeDatabase=fs.readFileSync(path.join(root,database.file),'utf8');
  const beforeBaseline=fs.existsSync(baselineFile)?fs.readFileSync(baselineFile,'utf8'):null;
  const beforeCatalogs=Object.fromEntries(catalogs.files.map(file=>{generation.targetPath(root,file);return [file,fs.existsSync(path.join(root,file))?fs.readFileSync(path.join(root,file),'utf8'):null];}));
  const records=database.load(root,JSON.parse(beforeDatabase));
  const currentCatalogs=Object.fromEntries(Object.entries(beforeCatalogs).map(([file,text])=>[file,text===null?null:JSON.parse(text)]));
  const read=source=>fs.existsSync(path.join(root,source))?fs.readFileSync(path.join(root,source),'utf8'):null;
  const result=plan(input,beforeBaseline&&!args.includes('--initialize')?JSON.parse(beforeBaseline):null,read,records,currentCatalogs);
  const excluded=JSON.parse(read('data/equipment/native-map.json')||'{}').unreleased_items||{};
  const models=Object.values(result.database.entities).flatMap(e=>e.collections?.武器型号资料?.rows||[]);
  for(const uid of Object.keys(excluded)){
    assert(!models.some(r=>r.data.装备UID===uid||r.data.variants?.some(v=>v.uid===uid)),'Unreleased weapon in import: '+uid);
    assert(!result.catalogs['data/equipment/crafting.json']?.items?.[uid],'Unreleased item in crafting import: '+uid);
  }
  const outputs=result.pages.filter(p=>p.raw!==p.before);
  generation.plan(root,Object.fromEntries(result.pages.map(p=>[p.source,p.raw])),registry,'tools/equipment/import.cjs@v1');
  const inputs=require('./catalog.cjs').data(root,result.database);
  for(const row of result.pages)validatePage(row,inputs);
  fs.mkdirSync(path.dirname(outputPath),{recursive:true});
  fs.mkdirSync(outputPath);
  for(const row of outputs)fs.writeFileSync(path.join(outputPath,filenames.get(row.source)),row.raw);
  const recordsText=reviewedJson(require('../identity.cjs').stored(result.database),beforeDatabase);
  const baselineText=reviewedJson(result.baseline,beforeBaseline);
  fs.writeFileSync(path.join(outputPath,'records.json'),recordsText);
  fs.writeFileSync(path.join(outputPath,'native-baseline.json'),baselineText);
  const catalogPayloads=new Map();
  for(const file of new Set(result.catalogChanges.map(c=>c.file))){const dest=path.join(outputPath,file);fs.mkdirSync(path.dirname(dest),{recursive:true});catalogPayloads.set(file,json(result.catalogs[file]));fs.writeFileSync(dest,catalogPayloads.get(file));}
  fs.writeFileSync(path.join(outputPath,'result.json'),JSON.stringify({pages:result.pages.map(({before,raw,...r})=>r),catalogs:result.catalogChanges,unavailable:result.unavailable},null,2)+'\n');
  if(writeMode){
    const entry=(target,before,after,artifact)=>({target,before:hash(before),after:hash(after),artifact});
    const entries=result.pages.map(row=>entry(row.source,row.before,row.raw,filenames.get(row.source)));
    entries.push(entry(database.file,beforeDatabase,recordsText,'records.json'));
    for(const [file,before] of Object.entries(beforeCatalogs))entries.push(entry(file,before,catalogPayloads.get(file)??before,file));
    entries.push(entry(baselineSource,beforeBaseline,baselineText,'native-baseline.json'));
    install(root,{...request,review:path.relative(path.join(root,'dist'),outputPath),entries},python);
  }
  console.log(result.pages.length+' pages; '+outputs.length+' changed; '+result.catalogChanges.length+' catalog fields changed; '+result.unavailable.length+' unavailable inputs');
}
module.exports={plan,reviewNames,validatePage,resolvePython,main};if(require.main===module)main(process.argv.slice(2));
