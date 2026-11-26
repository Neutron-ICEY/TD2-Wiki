const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const catalog=require('../tools/equipment/catalog.cjs').data();
async function run(file,title,source){
const {document,container:host,all}=require('./editor-dom.cjs').create();
const raw=fs.readFileSync(source,'utf8');
const currentCatalog=structuredClone(catalog);
const user={id:1,name:'Admin',groups:['sysop'],rights:['edit']};
const values={wgNamespaceNumber:0,wgAction:'view',wgUserId:1,wgUserGroups:['sysop'],wgPageName:title,wgArticleId:999};
let catalogRequests=0,reads=0;
const mw={config:{get:name=>values[name]},util:{getUrl:()=>''},Api:class{
  async post(params){assert.equal(params.action,'parse');assert.equal(params.text,'{{#invoke:TD2编辑数据|export}}');catalogRequests++;return {parse:{text:'catalog'}};}
  async get(params){reads++;return params.rvprop?{curtimestamp:'2026-11-09T00:00:00Z',query:{userinfo:user,pages:[{title,ns:0,pageid:999,revisions:[{revid:10,parentid:9,timestamp:'2026-11-08T00:00:00Z',sha1:'fixture',slots:{main:{contentmodel:'wikitext',contentformat:'text/x-wiki',content:raw}}}]}]}}:{query:{userinfo:user,pages:[{title,ns:0,pageid:999,actions:{edit:true}}]}};}
}};
const window={addEventListener(){},removeEventListener(){},crypto:{randomUUID:()=> 'fixture'}};
const DOMParser=class{parseFromString(){return {querySelector:()=>({getAttribute:()=>JSON.stringify(currentCatalog)})};}};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),{mw,location:{origin:'https://td2.huijiwiki.com'},DOMParser,document,window,console,URL});
  const instance=await mw.td2EditorRuntime.open({onExit(){}});await instance.ready;
  assert.equal(catalogRequests,1);assert(reads>0);
  const statuses=all(host).filter(e=>e.attributes?.role==='status').map(e=>e.textContent);
  assert(statuses.includes('已载入当前版本，可以编辑。'),JSON.stringify(statuses));
  const root=host.children[0];assert.equal(root.dataset.dirty,'false');
  assert(!all(host).some(e=>e.tagName==='SELECT'||e.tagName==='INPUT'&&e.type==='checkbox'));
  assert(!all(host).some(e=>e.tagName==='INPUT'&&e.value===title));
  if(title==='5.11 Tactical'){
    assert(!all(host).some(e=>e.attributes?.['aria-label']==='选择来源'));
    assert(!all(host).some(e=>e.tagName==='BUTTON'&&/来源|公共规则|待确认/.test(e.textContent)));
    assert.deepEqual(all(host).filter(e=>e.tagName==='H2').map(e=>e.textContent),['编辑表单','其他资料','补充正文']);
    const input=all(host).find(e=>e.id==='equipment-body');assert(input);
    const before=input.value;input.value='TEST 本地补充';await input.emit('input');
    assert.equal(root.dataset.dirty,'true','Editing prose must enable saving');
    input.value=before;await input.emit('input');assert.equal(root.dataset.dirty,'false','Restoring the prose restores the original source');
  }
  if(title==='追悼'){
    const notes=all(host).filter(e=>e.dataset?.field?.startsWith('天赋脚注:'));
    const note=notes.find(e=>!raw.includes('|'+e.dataset.field+'='));
    const saves=all(host).filter(e=>e.tagName==='BUTTON'&&e.textContent==='保存');
    assert(note);assert.equal(saves.length,2);
    note.value='临时脚注';await note.emit('input');
    assert(saves.every(button=>!button.disabled));
    note.value='';await note.emit('input');
    assert.equal(root.dataset.dirty,'false');assert(saves.every(button=>button.disabled));
    note.value='保留我的脚注';await note.emit('input');
    const [,id,mode]=note.dataset.field.split(':');
    const entity=currentCatalog.options.equipmentCatalog[raw.match(/\|资料ID=([^\n|}]+)/)[1].trim()];
    entity.talents=entity.talents.filter(t=>t.id!==id||t.mode!==mode);
    const createElement=document.createElement;
    document.createElement=tag=>{
      const node=createElement(tag);
      if(tag==='dialog'){node.close=()=>{};node.showModal=()=>node.children[1].emit('click');}
      return node;
    };
    const readCount=reads;
    await all(host).find(e=>e.tagName==='FORM').emit('submit');
    assert.equal(catalogRequests,2);
    assert.equal(reads,readCount,'Stale catalog must stop before attempting the write transport');
    assert(all(host).some(e=>e.attributes?.role==='status'&&e.textContent.includes('可编辑字段已更新')));
    assert.equal(note.value,'保留我的脚注');assert.equal(root.dataset.dirty,'true');
    assert(saves.every(button=>button.disabled));
  }
  instance.dispose();assert.equal(host.children.length,0);
  console.log(title+': compiled Runtime/catalog/form passed');
}
(async()=>{for(const [title,source]of [['5.11 Tactical','brands/品牌套装-5.11 Tactical'],['政令进行式','gear-sets/装备组-政令进行式'],['追悼','exotic-gear/奇特装备-追悼'],['阿科斯塔护膝','exotic-gear/奇特装备-阿科斯塔护膝']])await run(process.argv[2],title,'wiki/pages/'+source+'.wiki');})().catch(error=>{console.error(error);process.exitCode=1;});
