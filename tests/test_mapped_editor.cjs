const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const local=require('../ui/editor/src/local-session.js'),db=require('../tools/equipment/database.cjs').load(),catalog=require('../tools/equipment/catalog.cjs').data(),page=require('../tools/equipment/page.cjs');
const source=name=>Object.values(db.entities).find(e=>require('../tools/identity.cjs').display(e)===name).source;
const raw=name=>fs.readFileSync(source(name),'utf8'),open=text=>local.create(text,[],catalog.options);
test('100 mapped pages roundtrip exactly and expose only human fields',()=>{
  for(const record of Object.values(db.entities)){
    const text=fs.readFileSync(record.source,'utf8'),session=open(text);
    assert.deepEqual(session.blockers,[],record.source);assert.deepEqual(session.validate(),[],record.source);assert.equal(session.serialize().raw,text);
    for(const key of ['默认允许主核心','简介','装备名称','效果资料','属性槽','mask图纸'])assert.equal(session.state.fields[key],undefined);
    for(const key of ['资料ID','装备名称','效果资料'])assert.throws(()=>session.edit(key,'test'),/READ_ONLY/);
  }
});
for(const name of ['5.11 Tactical','核心力量','追悼','投资者','阿科斯塔应急包'])test(name+' manual edits preview payload, save and reopen preserve all unrelated fields',()=>{
  const text=raw(name),s=open(text);s.editBody([s.state.body,'LOCAL TEST'].filter(Boolean).join('\n'));s.edit('其他机制','人工其他资料');
  const output=s.serialize().raw,after=open(output);assert.equal(after.state.fields.其他机制.value,'人工其他资料');assert(after.state.body.endsWith('LOCAL TEST'));assert.equal(after.serialize().raw,output);
  const a=page.read(text),b=page.read(output);for(const [key,value]of Object.entries(a.root.fields))if(key!=='其他机制')assert.equal(b.root.fields[key].value,value.value,key);
  assert.deepEqual(after.summary,s.summary);
});

test('untouched existing prose survives field save and changed prose is validated',()=>{
  for(const name of ['5.11 Tactical','政令进行式','追悼']){
    const prose='\n\n参考：[https://example.com 既有攻略链接]\n',text=raw(name).trimEnd()+prose,s=open(text);
    assert.deepEqual(s.blockers,[]);assert.equal(s.serialize().raw,text);
    s.edit('其他机制','NON-GAME-FACT 本地来源');
    const output=s.serialize().raw;assert(output.endsWith(prose));assert.equal(open(output).serialize().raw,output);
    s.editBody(s.state.body+' changed');assert.throws(()=>s.serialize(),/双括号/);
  }
});

test('unknown identity, duplicated parameters, retired fields and unsafe text block saving',()=>{
  const text=raw('追悼');for(const bad of [text.replace(/exotic:[a-f0-9]+/,'exotic:unknown'),text.replace('|资料ID=','|常规获取=是\n|资料ID='),text.replace('|资料ID=','|资料ID=duplicate\n|资料ID=')])assert.throws(()=>open(bad).serialize(),/SAVE_BLOCKED/);
  const s=open(text);s.edit('其他机制','<script>alert(1)</script>');assert.throws(()=>s.serialize(),/不支持/);
});

test('core configurations distinguish simultaneous cores from random choices',()=>{
  const core=Object.values(db.entities).find(e=>e.source===source('核心力量'));
  assert.deepEqual(core.rules.find(r=>r.id==='slot:backpack').core,{count:3,selection:'fixed',types:['red','blue','yellow']});
  assert.deepEqual(core.rules.find(r=>r.id==='slot:mask').core,{count:1,selection:'random',types:['red','blue','yellow']});
  for(const [name,count,selection]of [['追悼',3,'预设'],['投资者',1,'随机']]){
    const e=Object.values(db.entities).find(e=>e.source===source(name)),slots=e.slots.filter(r=>r.类型==='主属性');assert.equal(slots.length,count);assert(slots.every(r=>r.选择方式===selection));
  }
});
test('mapped records keep native blueprint source links',()=>{
  const data=require('../tools/exotic_gear/data.cjs').snapshot();for(const [id,e]of Object.entries(db.entities))if(e.template==='奇特装备信息'){
    for(const [key,purpose]of [['制作图纸','craft'],['重新配置图纸','reconfigure']])for(const ref of (e.fields[key]||'').split(';').filter(Boolean))assert(data.blueprints.some(b=>b.id===ref&&b.target_id===id&&b.purpose===purpose));
  }
});
test('save conflicts and unknown outcomes require reread; success reopens exact human state',async()=>{
  const site=require('../ui/editor/src/site-session.js');
  for(const fault of ['conflict','unknown',null]){
    let writes=0,revision={title:'追悼',pageid:1,revid:1,raw:raw('追悼')};const adapter={load:async()=>({...revision}),save:async(base,text,verify)=>{
      writes++;if(fault==='conflict')throw Object.assign(new Error('editconflict'),{code:'editconflict'});if(fault==='unknown')throw Object.assign(new Error('timeout'),{outcome:'UNKNOWN'});verify();revision={...revision,revid:2,raw:text};return {revision};
    }};
    const s=site.create(adapter,[],catalog.options);await s.load();await s.save();assert.equal(writes,0);s.editor.editBody('LOCAL TEST');
    if(fault){await assert.rejects(s.save());await assert.rejects(s.save(),/RELOAD_REQUIRED/);assert.equal(writes,1);}
    else {await s.save();assert.equal(s.status,'VERIFIED');assert.equal(s.contentDirty,false);assert.equal(s.editor.state.body,'LOCAL TEST');}
  }
});
