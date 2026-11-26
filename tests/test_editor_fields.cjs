const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const db=require('../tools/equipment/database.cjs').load(),catalog=require('../tools/equipment/catalog.cjs').data();
const local=require('../ui/editor/src/local-session.js'),mappedUI=require('../ui/editor/src/mapped-ui.js');
const api={uiPrimitives:require('../ui/editor/src/ui-primitives.js')};

test('all pages offer only human fields and body, while automatic facts stay in Reader',()=>{
 for(const e of Object.values(db.entities)){
  const text=fs.readFileSync(e.source,'utf8'),session=local.create(text,[],catalog.options),dom=require('./editor-dom.cjs').create();
  mappedUI({...dom,session,api,onChange(){}});
  const nodes=dom.all(dom.container);
  const notes=['装备组信息','奇特装备信息','武器信息'].includes(e.template)?e.effects.filter(r=>r.名称).length:0;
  assert.deepEqual(nodes.filter(n=>n.tagName==='H2').map(n=>n.textContent),[...(notes?['天赋脚注']:[]),'其他资料','补充正文']);
  assert.equal(nodes.filter(n=>n.tagName==='TEXTAREA').length,notes+2);
  assert(!nodes.some(n=>['SELECT','DETAILS','BUTTON'].includes(n.tagName)));
  assert.equal(session.serialize().raw,text,e.source);
  assert.deepEqual(Object.keys(session.summary),['template','title',...(['装备组信息','奇特装备信息','武器信息'].includes(e.template)?['talents']:[])]);
 }
});

test('other-information edits save and reopen without recreating named or acquisition fields',()=>{
 for(const title of ['戈兰装备有限公司','5.11 Tactical','核心力量','追悼']){
  const e=Object.values(db.entities).find(e=>require('../tools/identity.cjs').display(e)===title);
  const session=local.create(fs.readFileSync(e.source,'utf8'),[],catalog.options);
  session.edit('其他机制','LOCAL TEST');session.editBody('BODY TEST');
  const output=session.serialize().raw,again=local.create(output,[],catalog.options);
  assert.equal(again.state.fields.其他机制.value,'LOCAL TEST');assert.equal(again.state.body,'BODY TEST');
  assert(!/装备获取说明|图纸获取说明|具名装备资料/.test(output));
  assert.equal(again.serialize().raw,output);
 }
});
