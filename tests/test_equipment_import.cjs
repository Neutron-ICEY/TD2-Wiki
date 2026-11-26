'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const page=require('../tools/equipment/page.cjs'),{merge}=require('../tools/equipment/merge.cjs'),{plan}=require('../tools/equipment/import.cjs'),{sync}=require('../tools/equipment/sync.cjs');
const effects=require('../ui/editor/src/page-effects.js'),local=require('../ui/editor/src/local-session.js'),catalog=require('../tools/equipment/catalog.cjs').data();
const target=(id,mode,field)=>({records:[{field:'效果资料',id:{效果ID:id,模式:mode},template:'装备效果'}],field});
test('all current pages reopen exactly and effect edits retain unrelated data',()=>{
  let count=0;
  for(const group of ['brands','equipment','gear-sets','exotic-gear'])for(const file of fs.readdirSync(path.join(__dirname,'../wiki/pages',group))){
    if(!file.endsWith('.wiki'))continue;
    const raw=fs.readFileSync(path.join(__dirname,'../wiki/pages',group,file),'utf8'),s=local.create(raw,catalog.catalog,catalog.options);
    assert.deepEqual(s.blockers,[],file);const normalized=s.serialize().raw;assert.equal(local.create(normalized,catalog.catalog,catalog.options).serialize().raw,normalized,file);
    s.edit('其他机制','本地人工说明');const output=s.serialize().raw;assert.equal(local.create(output,[],catalog.options).state.fields.其他机制.value,'本地人工说明');
    count++;
  }
  assert.equal(count,102);
});
test('new stable records import fieldwise; changed name cannot replace human notes',()=>{
  const raw='{{装备组信息\n|装备组名称=测试\n|装备资料={{装备组装备|装备UID=A|装备名称=人工名称|来源说明=人工说明}}\n}}',t=field=>({field,records:[{field:'装备资料',id:{装备UID:'A'},template:'装备组装备'}]});
  const a={target:t('装备名称'),value:'原生旧名',semantic:'旧'},initial=merge(raw,null,{schema_version:1,units:[a]});
  const newer={target:t('装备名称'),value:'原生新名',semantic:'新'},added={target:{field:'装备名称',records:[{field:'装备资料',id:{装备UID:'B'},template:'装备组装备'}]},value:'新增型号',semantic:'新增型号'};
  const result=merge(raw,initial.baseline,{schema_version:1,units:[newer,added]});
  assert.equal(page.value(page.read(result.raw),t('来源说明')),'人工说明');assert.equal(page.value(page.read(result.raw),added.target),'新增型号');
  assert.throws(()=>plan({schema_version:1,entities:[{id:'a',source:'wiki/pages/gear-sets/a.wiki',template:'装备组信息',units:[newer,newer]}]},null,()=>raw.replace('{{装备组信息','{{装备组信息|资料ID=a')),/Duplicate native target/);
});
test('remote local edits reconcile by record identity and block the same changed field',()=>{
  const base='{{装备组信息\n|装备组名称=测试\n|英文原名=Test\n|简介=原文\n}}\n正文',here=base.replace('Test','Local'),remote=base.replace('原文','线上修订');
  assert.equal(sync(base,here,remote).raw,here.replace('原文','线上修订'));
  assert(sync(base,here,base.replace('Test','Remote')).conflicts.length);
});
test('sync keeps both outside text changes and independently added stable records',()=>{
  const base='<!--base-->\n{{装备组信息\n|装备组名称=测试\n|装备资料={{装备组装备|装备UID=A|装备名称=原名|来源说明=说明}}\n}}\n正文';
  const here=base.replace('来源说明=说明','来源说明=本地说明');
  const remote=base.replace('<!--base-->','<!--longer remote prefix-->').replace('正文','线上正文').replace('装备名称=原名','装备名称=线上名称').replace('}}\n}}','}}{{装备组装备|装备UID=B|装备名称=新增}}\n}}');
  const result=sync(base,here,remote);assert.deepEqual(result.conflicts,[]);
  assert(result.raw.startsWith('<!--longer remote prefix-->\n'));assert(result.raw.endsWith('\n线上正文'));
  assert(result.raw.includes('{{装备组装备|装备UID=A|装备名称=线上名称|来源说明=本地说明}}'));
  assert.equal(page.value(page.read(result.raw),{field:'装备名称',records:[{field:'装备资料',id:{装备UID:'B'},template:'装备组装备'}]}),'新增');
  for(const changed of [base.replace('|来源说明=说明',''),base.replace('{{装备组装备|装备UID=A|装备名称=原名|来源说明=说明}}','')]){
    const conflict=sync(base,here,changed);assert(conflict.conflicts.length);assert.equal(conflict.raw,here);
  }
  const conflict=sync(base,here.replace('正文','本地正文'),remote);assert(conflict.conflicts.length);assert.equal(conflict.raw,here.replace('正文','本地正文'));
});

test('review outputs use registration IDs across equal basenames and reject wrong identity',()=>{
  const {reviewNames}=require('../tools/equipment/import.cjs');
  const pages=[{id:'brand:a',source:'wiki/pages/brands/相同.wiki'},{id:'set:b',source:'wiki/pages/gear-sets/相同.wiki'}];
  const registry={entries:pages.map((p,i)=>({id:'page-'+i,source:p.source,related_entity:p.id,kind:'pages',namespace:0,ownership:'generated',generator:'tools/equipment/import.cjs@v1'}))};
  assert.deepEqual([...reviewNames(pages,registry).values()],['page-0.wiki','page-1.wiki']);
  registry.entries[1].related_entity='brand:a';assert.throws(()=>reviewNames(pages,registry),/Register the page/);
  registry.entries[1].related_entity='set:b';registry.entries[1].id='PAGE-0';assert.throws(()=>reviewNames(pages,registry),/Duplicate review/);
});
