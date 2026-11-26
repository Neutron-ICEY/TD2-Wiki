const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const editorSource=process.env.TD2_EDITOR_SOURCE||path.resolve(__dirname,'../ui/editor/src');
const mount=require(path.join(editorSource,'site-expanded-bootstrap.js')).mount;
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.events={};this.scrolls=[];this.style={};}
  append(...nodes){for(const n of nodes){n.parent=this;this.children.push(n);}}
  prepend(node){node.parent=this;this.children.unshift(node);}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(k,f){(this.events[k]??=[]).push(f);}
  removeEventListener(k,f){this.events[k]=(this.events[k]||[]).filter(x=>x!==f);}
  querySelectorAll(selector){return this.children.flatMap(n=>[...(selector.split(',').includes(n.tag)?[n]:[]),...n.querySelectorAll(selector)]);}
  scrollIntoView(options){this.scrolls.push(options);}
  focus(){this.focused=true;}
  replaceChildren(){this.children=[];}
  remove(){this.parent.children=this.parent.children.filter(n=>n!==this);}
  async emit(type,extra={}){for(const f of this.events[type]||[])await f({preventDefault(){},...extra});}
}
function setup(options={}){
  const host=new Element('host'),head=new Element('head'),win=new Element('window');
  let loads=0,saves=0,previews=0,exits=0,creates=0,release,summaryInput,viewChanged;
  const confirmations=[];
  const input=new Element('input');input.id='sample';input.value='before';
  win.crypto={randomUUID:()=> 'test'};win.confirm=message=>{confirmations.push(message);return typeof options.confirm==='function'?options.confirm(message):options.confirm!==false;};
  win.getComputedStyle=element=>({position:element.position});
  const controller={busy:false,dirty:false,contentDirty:false,status:'READY',summary:'',base:{revid:1},state:{},editor:{},
    async load(){loads++;},preview(){return options.serialize?options.serialize(input.value):'same form';},
    async save(){saves++;this.busy=true;await new Promise(r=>release=r);this.busy=false;this.contentDirty=false;this.summary='';this.dirty=false;},
    noteInput(v){this.contentDirty=v;this.dirty=v||this.summary!=='';},setSummary(v){this.summary=v;this.dirty=v!==''||this.contentDirty;},dispose(){}};
  const document={head,createElement:tag=>{const node=new Element(tag);if(tag==='dialog'){node.close=()=>{};node.showModal=()=>{confirmations.push(node.children[0].textContent);if(!options.manualConfirm){const approved=typeof options.confirm==='function'?options.confirm(node.children[0].textContent):options.confirm!==false;node.children[approved?1:2].emit('click');}};}return node;},getElementById:()=>host,querySelector:()=>null,querySelectorAll:selector=>selector==='#skin-root, .skin-subnav'?(options.navigation||[]):host.children};
  const lab={siteSession:{create(){creates++;return controller;}},uiPrimitives:{create:()=>({Field:({control})=>{summaryInput=control;return {element:new Element('label'),setError(){}};}})},readerPreview:{create:()=>({invalidate(){},async show(raw){previews++;return options.preview?await options.preview(raw):{};},dispose(){}})},editorView:{create:({container,onChange})=>{viewChanged=onChange;container.replaceChildren();container.append(input);if(options.changeDuringRender)onChange();return {validate:()=>options.valid!==false};}}};
  const adapter={};
  const instance=mount({document,window:win,lab,config:{version:'test',options:{bonusData:{}}},adapter,onExit:()=>exits++});
  const root=host.children[0],form=root.children.find(x=>x.tag==='form');
  const bars=[form.children[0],form.children[2].children[2]];
  return {instance,controller,win,form,bars,host,head,input,summaryInput,adapter,confirmations,viewChanged:()=>viewChanged(),status:form.children[2].children[1],container:form.children[1].children[0],previewArea:root.children[2],counts:()=>({loads,saves,previews,exits,creates}),release:()=>release()};
}

test('list callbacks refresh pending input when controls return to their loaded values',async()=>{
  const t=setup({changeDuringRender:true});await t.instance.ready;assert.equal(t.controller.contentDirty,false);
  t.input.value='temporary selection';await t.container.emit('change');assert.equal(t.controller.contentDirty,true);
  t.input.value='before';t.viewChanged();assert.equal(t.controller.contentDirty,false);
  assert(t.bars.every(b=>b.children[1].disabled));await t.form.emit('submit');assert.equal(t.counts().saves,0);
  t.input.value='changed';t.viewChanged();assert.equal(t.controller.contentDirty,true);assert(t.bars.every(b=>!b.children[1].disabled));
  t.instance.dispose();
});

test('both preview bars share one pending request and recover after success',async()=>{
  for(const index of [0,1]){
    const completions=[],t=setup({preview:()=>new Promise(resolve=>completions.push(resolve))});await t.instance.ready;
    const pending=t.bars[index].children[0].emit('click');
    assert(t.bars.every(b=>b.children[0].disabled));
    assert.equal(t.form.children[1].disabled,false);assert.equal(t.summaryInput.disabled,false);
    assert.equal(t.controller.dirty,false);assert(t.bars.every(b=>b.children[1].disabled));
    await t.bars[index].children[0].emit('click');await t.bars[1-index].children[0].emit('click');
    assert.equal(t.counts().previews,1);assert.equal(t.previewArea.scrolls.length,1);
    completions.shift()({});await pending;assert(t.bars.every(b=>!b.children[0].disabled));
    const next=t.bars[1-index].children[0].emit('click');assert.equal(t.counts().previews,2);
    completions.shift()({});await next;assert(t.bars.every(b=>!b.children[0].disabled));t.instance.dispose();
  }
});

test('preview rejection and serialization failure restore both controls for retry',async()=>{
  for(const failure of ['request','serialize']){
    let fail=true,reject;
    const t=setup({serialize:()=>{if(fail&&failure==='serialize')throw new Error('SERIALIZE_FAILED');return 'same form';},preview:()=>fail?new Promise((resolve,no)=>reject=no):{}});
    await t.instance.ready;const pending=t.bars[0].children[0].emit('click');
    if(failure==='request'){assert(t.bars.every(b=>b.children[0].disabled));reject(new Error('PARSE_FAILED'));}
    await pending;assert(t.bars.every(b=>!b.children[0].disabled));assert.match(t.status.textContent,/_FAILED/);
    assert.equal(t.controller.dirty,false);assert(t.bars.every(b=>b.children[1].disabled));
    fail=false;await t.bars[1].children[0].emit('click');
    assert.equal(t.counts().previews,failure==='request'?2:1);assert(t.bars.every(b=>!b.children[0].disabled));t.instance.dispose();
  }
});

test('input stays editable during preview and the next request uses the latest input',async()=>{
  const calls=[],completions=[],t=setup({serialize:value=>value,preview:raw=>{calls.push(raw);return new Promise(resolve=>completions.push(resolve));}});
  await t.instance.ready;const pending=t.bars[0].children[0].emit('click');
  t.input.value='latest input';await t.container.emit('input');
  assert.equal(t.input.value,'latest input');assert.equal(t.controller.contentDirty,true);
  assert.equal(t.form.children[1].disabled,false);assert(t.bars.every(b=>!b.children[1].disabled&&b.children[0].disabled));
  await t.bars[1].children[0].emit('click');assert.deepEqual(calls,['before']);
  completions.shift()(null);await pending;assert.equal(t.previewArea.scrolls.length,1);
  const next=t.bars[1].children[0].emit('click');assert.deepEqual(calls,['before','latest input']);
  completions.shift()({});await next;assert.equal(t.input.value,'latest input');assert.equal(t.controller.contentDirty,true);
  t.instance.dispose();
});

test('preview completion does not release save busy state or change dirty state',async()=>{
  let finish;const t=setup({preview:()=>new Promise(resolve=>finish=resolve)});await t.instance.ready;
  t.input.value='changed';await t.container.emit('input');const pending=t.bars[0].children[0].emit('click');
  assert(t.bars.every(b=>!b.children[1].disabled));const saving=t.form.emit('submit');await Promise.resolve();
  assert.equal(t.counts().saves,1);assert.equal(t.controller.busy,true);
  finish({});await pending;assert(t.bars.every(b=>b.children[0].disabled&&b.children[1].disabled));
  t.release();await saving;assert.equal(t.controller.dirty,false);assert(t.bars.every(b=>!b.children[0].disabled&&b.children[1].disabled));
  t.instance.dispose();
});

test('disposed preview success or failure cannot affect a new editor instance',async()=>{
  for(const fails of [false,true]){
    let resolveOld,rejectOld,resolveNew;
    const old=setup({preview:()=>new Promise((resolve,reject)=>{resolveOld=resolve;rejectOld=reject;})});await old.instance.ready;
    const pendingOld=old.bars[0].children[0].emit('click');
    await old.bars[1].children[2].emit('click');const status=old.status.textContent;
    assert.equal(old.host.children.length,0);assert.equal(old.head.children.length,0);
    assert.equal(old.win.events.pageshow.length,0);assert.equal(old.container.events.input.length,0);
    await old.bars[0].children[0].emit('click');assert.equal(old.counts().previews,1);
    const next=setup({preview:()=>new Promise(resolve=>resolveNew=resolve)});await next.instance.ready;
    assert(next.bars.every(b=>!b.children[0].disabled));const pendingNew=next.bars[1].children[0].emit('click');
    if(fails)rejectOld(new Error('LATE_FAILURE'));else resolveOld({});await pendingOld;
    assert.equal(old.status.textContent,status);assert.equal(old.previewArea.scrolls.length,1);
    assert(next.bars.every(b=>b.children[0].disabled));assert.equal(next.counts().previews,1);
    resolveNew({});await pendingNew;assert(next.bars.every(b=>!b.children[0].disabled));next.instance.dispose();
  }
});

test('Reader preview generation still discards responses after input invalidation or disposal',async()=>{
  const create=require(path.join(editorSource,'reader-preview.js')).create;
  for(const action of ['invalidate','dispose']){
    let finish;const container=new Element('section'),document={createElement:tag=>new Element(tag)};
    const preview=create({document,container,adapter:{preview:()=>new Promise(resolve=>finish=resolve)}});
    const frame=container.children[2],pending=preview.show('first input');preview[action]();finish({html:'must not render'});
    assert.equal(await pending,null);assert.equal(frame.srcdoc,undefined);
    if(action==='invalidate')preview.dispose();assert.equal(container.children.length,0);
  }
});
test('both bars share preview, one submit handler and busy state',async()=>{
  const t=setup();await t.instance.ready;
  assert.deepEqual(t.bars.map(b=>b.children.map(n=>n.textContent)),Array(2).fill(['预览','保存','返回页面','重读数据']));
  for(const b of t.bars){assert.equal(b.children[1].type,'submit');await b.children[0].emit('click');}
  assert.equal(t.counts().previews,2);assert.equal(t.form.events.submit.length,1);
  t.input.value='after';await t.container.emit('input');
  const saving=t.form.emit('submit');await Promise.resolve();
  for(const b of t.bars){for(const n of b.children.filter(n=>n.tag==='button'))assert.equal(n.disabled,true);}
  await t.form.emit('submit');assert.equal(t.counts().saves,1);
  assert.deepEqual(t.confirmations,['确认保存当前修改？']);
  t.release();await saving;
  assert.equal(t.counts().previews,2);
  for(const b of t.bars)assert.equal(b.children[1].disabled,true);
  assert.equal(t.counts().creates,1);
});
test('unchanged content, summary-only edits and restored input cannot submit',async()=>{
  const t=setup();await t.instance.ready;
  const disabled=()=>t.bars.every(b=>b.children[1].disabled);
  assert.equal(disabled(),true);await t.form.emit('submit');assert.equal(t.counts().saves,0);
  t.summaryInput.value='summary only';await t.summaryInput.emit('input');
  assert.equal(t.controller.dirty,true);assert.equal(disabled(),true);await t.form.emit('submit');assert.equal(t.counts().saves,0);
  assert.equal(t.confirmations.length,0);
  t.input.value='changed';await t.container.emit('input');assert.equal(disabled(),false);
  t.input.value='before';await t.container.emit('input');assert.equal(disabled(),true);
  t.input.value='changed';await t.container.emit('change');assert.equal(disabled(),false);
  const saving=t.form.emit('submit');await Promise.resolve();assert.equal(disabled(),true);t.release();await saving;
  assert.equal(disabled(),true);assert.equal(t.counts().saves,1);
});
test('content changes still cannot submit when reload or transport protection blocks saving',async()=>{
  for(const block of ['reload','halted']){const t=setup();await t.instance.ready;
    if(block==='reload')t.controller.needsReload=true;else t.adapter.halted=true;
    t.input.value='changed';await t.container.emit('input');
    assert(t.bars.every(b=>b.children[1].disabled));await t.form.emit('submit');assert.equal(t.counts().saves,0);
    assert.equal(t.confirmations.length,0);
  }
});
test('both save controls confirm before submitting; cancelling preserves content and summary',async()=>{
  for(const index of [0,1]){let approved=false;const t=setup({confirm:()=>approved});await t.instance.ready;
    t.input.value='changed';await t.container.emit('input');t.summaryInput.value='summary';await t.summaryInput.emit('input');
    await t.form.emit('submit',{submitter:t.bars[index].children[1]});
    assert.deepEqual(t.confirmations,['确认保存当前修改？']);assert.equal(t.counts().saves,0);
    assert.equal(t.input.value,'changed');assert.equal(t.summaryInput.value,'summary');assert.equal(t.controller.summary,'summary');
    assert.equal(t.controller.contentDirty,true);assert(t.bars.every(b=>!b.children[1].disabled));
    approved=true;const saving=t.form.emit('submit',{submitter:t.bars[index].children[1]});await Promise.resolve();
    assert.equal(t.counts().saves,1);assert.deepEqual(t.confirmations,Array(2).fill('确认保存当前修改？'));
    await t.form.emit('submit');assert.equal(t.confirmations.length,2);assert.equal(t.counts().saves,1);
    t.release();await saving;assert(t.bars.every(b=>b.children[1].disabled));
  }
});
test('invalid fields or summary do not open a save confirmation',async()=>{
  for(const invalid of ['fields','summary']){const t=setup({valid:invalid!=='fields'});await t.instance.ready;
    t.input.value='changed';await t.container.emit('input');
    if(invalid==='summary'){t.summaryInput.value=' invalid';await t.summaryInput.emit('input');}
    await t.form.emit('submit');assert.equal(t.confirmations.length,0);assert.equal(t.counts().saves,0);
    if(invalid==='summary')assert.equal(t.summaryInput.focused,true);
  }
});
test('preview immediately scrolls to its loading area; invalid input stays in the form',async()=>{
  let finish;const t=setup({preview:()=>new Promise(resolve=>finish=resolve)});await t.instance.ready;
  const pending=t.bars[0].children[0].emit('click');
  assert.equal(t.counts().previews,1);assert.deepEqual(t.previewArea.scrolls,[{block:'start'}]);
  finish({});await pending;assert.deepEqual(t.previewArea.scrolls,[{block:'start'},{block:'start'}]);
  const invalid=setup({valid:false});await invalid.instance.ready;await invalid.bars[1].children[0].emit('click');
  assert.equal(invalid.counts().previews,0);assert.equal(invalid.previewArea.scrolls.length,0);
});
test('stale previews and disposed forms do not scroll again after the request completes',async()=>{
  for(const outcome of ['stale','disposed']){let finish;const t=setup({preview:()=>new Promise(resolve=>finish=resolve)});await t.instance.ready;
    const pending=t.bars[0].children[0].emit('click');assert.equal(t.previewArea.scrolls.length,1);
    if(outcome==='disposed')t.instance.dispose();finish(outcome==='stale'?null:{});await pending;
    assert.equal(t.previewArea.scrolls.length,1);
  }
});
test('preview positioning clears both navigation bars and remeasures after rendering',async()=>{
  let finish,bottom=100;
  const navigation=[
    {position:'fixed',getBoundingClientRect:()=>({width:1280,bottom:50})},
    {position:'sticky',getBoundingClientRect:()=>({width:1280,bottom})},
    {position:'static',getBoundingClientRect:()=>({width:1280,bottom:500})},
    {position:'fixed',getBoundingClientRect:()=>({width:0,bottom:700})}
  ];
  const t=setup({navigation,preview:()=>new Promise(resolve=>finish=resolve)});await t.instance.ready;
  const pending=t.bars[1].children[0].emit('click');
  assert.equal(t.previewArea.style.scrollMarginTop,'116px');
  bottom=120;finish({});await pending;
  assert.equal(t.previewArea.style.scrollMarginTop,'136px');
  assert.equal(t.previewArea.scrolls.length,2);
  const plain=setup();await plain.instance.ready;await plain.bars[0].children[0].emit('click');
  assert.equal(plain.previewArea.style.scrollMarginTop,'16px');
});
test('top and bottom return use the same dirty confirmation and dispose',async()=>{
  for(const index of [0,1]){const t=setup({confirm:false});await t.instance.ready;t.controller.dirty=true;
    await t.bars[index].children[2].emit('click');assert.equal(t.counts().exits,0);
    t.win.confirm=()=>true;await t.bars[index].children[2].emit('click');assert.equal(t.counts().exits,1);assert.equal(t.host.children.length,0);
  }
});

test('page confirmation blocks duplicate submits and disposal cannot save',async()=>{
  for(const action of ['cancel','dispose','accept']){
    const t=setup({manualConfirm:true});await t.instance.ready;
    t.input.value='changed';await t.container.emit('input');
    const saving=t.form.emit('submit');assert.equal(t.counts().saves,0);
    assert(t.bars.every(b=>b.children[1].disabled));assert(t.form.children[1].disabled);
    await t.form.emit('submit');assert.equal(t.confirmations.length,1);
    const dialog=t.host.children[0].children.find(e=>e.tag==='dialog');
    if(action==='dispose')t.instance.dispose();
    else if(action==='cancel')await dialog.emit('cancel');
    else {await dialog.children[1].emit('click');assert.equal(t.counts().saves,1);t.release();}
    await saving;
    assert.equal(t.counts().saves,action==='accept'?1:0);
    if(action==='cancel'){assert.equal(t.input.value,'changed');assert(!t.form.children[1].disabled);}
  }
});
