const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const reader = fs.readFileSync(path.join(root, 'ui/brand-sets/brand-sets.js'), 'utf8');
const entry = fs.readFileSync(path.join(root, 'ui/editor/src/site-entry.js'), 'utf8');
const policy = require('../ui/editor/src/site-entry-policy');
const raw = fs.readFileSync(path.join(root, 'wiki/pages/brands/品牌套装-5.11 Tactical.wiki'), 'utf8');

// 页面操作的 DOM 合同；布局和真实剪贴板另由浏览器预览验证。
class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.events = {}; this.dataset = {}; this.style = {}; this.className = ''; this.nodeType = 1; }
  appendChild(node) { node.remove(); this.children.push(node); node.parentElement = this; return node; }
  append(...nodes) { nodes.forEach(node => this.appendChild(node)); }
  insertBefore(node, ref) { node.remove(); const i = this.children.indexOf(ref); this.children.splice(i < 0 ? this.children.length : i, 0, node); node.parentElement = this; }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(n => n !== this); this.parentElement = null; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  removeAttribute(k) { delete this.attributes[k]; }
  addEventListener(k, fn) { this.events[k] = fn; }
  matches(s) { return s.split(',').some(t => { t=t.trim(); return t[0]==='#' ? this.id===t.slice(1) : t[0]==='.' ? this.className.split(' ').includes(t.slice(1)) : t[0]==='[' ? Object.hasOwn(this.attributes,t.slice(1,-1)) : this.tagName===t.toUpperCase(); }); }
  querySelectorAll(s) { return this.children.flatMap(n => [...(n.matches(s) ? [n] : []), ...n.querySelectorAll(s)]); }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  getElementById(id) { return this.querySelector('#' + id); }
  closest(s) { for(let n=this;n;n=n.parentElement) if(n.matches(s)) return n; return null; }
  focus() { this.focused = true; }
  get classList() { return {contains: n => this.className.split(' ').includes(n), toggle: (n, on) => { this.className = this.className.split(' ').filter(c => c !== n).concat(on ? [n] : []).join(' '); }}; }
}
const flush = async () => { for(let i=0;i<16;i++) await Promise.resolve(); };
function setup(options = {}) {
  const title = options.form ? '品牌套装-5.11 Tactical' : '威胁度';
  const values = {wgPageName:title, wgArticleId:903, wgNamespaceNumber:0, wgAction:'view', wgIsArticle:true,
    wgUserId:options.role==='admin'?1:options.role==='user'?2:0, wgUserName:options.role==='admin'?'Admin':null,
    wgUserGroups:options.role==='admin'?['sysop','verified']:options.role==='user'?['user','verified']:['*'], ...options.config};
  const doc = new Element('document'); doc.readyState='complete'; doc.body=doc; doc.documentElement=doc; doc.createElement=tag=>new Element(tag);
  const heading = new Element('header'); heading.id='firstHeading'; doc.appendChild(heading);
  const native = new Element('a'); native.id='ca-edit'; native.textContent='skin edit'; heading.appendChild(native);
  const canonical = new Element('link'); canonical.href='https://td2.huijiwiki.com/wiki/' + encodeURIComponent(title);
  const query = doc.querySelector.bind(doc); doc.querySelector=s=>s==='link[rel="canonical"]'?canonical:query(s);
  const calls=[], copied=[], timers=[];
  const response = {query:{userinfo:{id:values.wgUserId,name:values.wgUserName,groups:values.wgUserGroups,rights:['edit']},pages:[{pageid:values.wgArticleId,title,ns:0,actions:{edit:true}}]}};
  if(options.deny) options.deny(response);
  const api = {get:async p=>{
    calls.push(p);
    if(options.networkError) throw Error('offline');
    if(options.defer) await options.defer;
    if(p.prop==='revisions') return {query:{pages:[{pageid:values.wgArticleId,title,revisions:[{slots:{main:{content:raw}}}]}]}};
    const result=JSON.parse(JSON.stringify(response));
    if(p.prop.includes('templates')) result.query.pages[0].templates=options.form?[{title:'Template:品牌套装信息'}]:[];
    return result;
  }};
  const mw = {config:{get:k=>values[k]},loader:{using:()=>Promise.resolve()},Api:function(){return api;},
    util:{getUrl:(t,params)=>'https://td2.huijiwiki.com/wiki/'+encodeURIComponent(t)+(params?'?'+new URLSearchParams(params):''),addPortletLink:()=>null},
    huijiApi:options.helper===null?null:{getPageUrlById:options.helper||((id,prefix)=>'https://'+prefix+'.huijiwiki.com/p/'+id)},
    td2EditorEntryPolicy:policy};
  const env={document:doc,mw,URL,console,location:{href:canonical.href+(options.query||''),origin:'https://td2.huijiwiki.com'},
    navigator:{clipboard:options.noClipboard?undefined:{writeText:options.writeText||(text=>{copied.push(text);return Promise.resolve();})}},
    setTimeout:fn=>timers.push(fn),clearTimeout:()=>{}};
  env.window=env;
  vm.runInNewContext(reader,env);
  return {doc,mw,env,values,response,calls,copied,timers,native,init:()=>doc._td2BrandSetsRuntime.init(doc),
    row:()=>doc.getElementById('td2-page-actions'),labels:()=>doc.getElementById('td2-page-actions')?.children.filter(n=>!n.hidden).map(n=>n.textContent||n.querySelector('a')?.textContent)};
}

test('guest and verified non-admin readers get copy only, even if edit is allowed', async()=>{
  for(const role of ['guest','user']) for(const form of [false,true]) {
    const h=setup({role,form}); await flush(); assert.deepEqual(h.labels(),['复制链接']); assert(h.native.hidden); assert.equal(h.calls.length,0);
    vm.runInNewContext(entry,h.env); await flush(); assert.equal(h.doc.getElementById('td2-js-edit-entry'),null);
  }
});
test('real Editor contract supplies form entry; manual mechanism has no form', async()=>{
  for(const form of [false,true]) {
    const h=setup({role:'admin',form}); vm.runInNewContext(entry,h.env); await h.mw.td2EditorEntryStart; await flush(); h.init();
    assert.deepEqual(h.labels(),form?['复制链接','编辑表单','编辑源码']:['复制链接','编辑源码']);
    assert.equal(h.doc.getElementById('ca-edit').href,h.mw.util.getUrl(h.values.wgPageName,{action:'edit'}));
    const count=h.calls.length;h.init();vm.runInNewContext(reader,h.env);await flush();assert.equal(h.calls.length,count);assert.equal(h.doc.querySelectorAll('#td2-page-actions').length,1);
  }
});
test('server permission, group, and page identity failures never expose edit controls',async()=>{
  for(const deny of [r=>r.query.pages[0].actions.edit=false,r=>r.query.userinfo.groups=['verified'],r=>r.query.userinfo.rights=[],
    r=>r.query.userinfo.id=9,r=>r.query.pages[0].pageid=2,r=>r.query.pages[0].title='同名装备',r=>r.query.pages[0].missing=true]){
    const h=setup({role:'admin',deny});await flush();assert.deepEqual(h.labels(),['复制链接']);assert(h.native.hidden);
  }
  const offline=setup({role:'admin',networkError:true});await flush();assert.deepEqual(offline.labels(),['复制链接']);
});
test('historical views copy current page; non-content actions have no toolbar',async()=>{
  for(const query of ['?oldid=1','?diff=2']){const h=setup({role:'admin',query});await flush();assert.deepEqual(h.labels(),['复制链接']);assert.equal(h.calls.length,0);}
  for(const config of [{wgNamespaceNumber:-1},{wgNamespaceNumber:10},{wgNamespaceNumber:1},{wgAction:'edit'},{wgIsArticle:false}])assert.equal(setup({config}).row(),null);
});
test('late permission responses cannot add controls to a different page',async()=>{
  let release;const defer=new Promise(resolve=>{release=resolve;});const h=setup({role:'admin',defer});const old=h.row();h.values.wgPageName='新页面';h.values.wgArticleId=904;h.init();release();await flush();assert.equal(old.parentElement,null);assert.deepEqual(h.labels(),['复制链接']);
});
test('official PID URLs, canonical fallback, and clipboard feedback',async()=>{
  for(const options of [{},{helper:null},{helper:()=>'/index.php?curid=903'}]){
    const h=setup(options);h.row().children[0].events.click();await flush();assert.deepEqual(h.copied,['https://td2.huijiwiki.com/p/903']);assert.equal(h.row().children[0].textContent,'成功复制');assert.equal(h.doc.querySelector('textarea'),null);h.timers.at(-1)();assert.equal(h.row().children[0].textContent,'复制链接');
  }
  for(const options of [{config:{wgArticleId:0}},{config:{wgArticleId:-1}},{config:{wgArticleId:1.5}},{config:{wgArticleId:undefined}},
    {helper:()=>'/p/999'},{helper:()=> 'https://other.test/p/903'},{helper:()=>{throw Error('unavailable');}}]){
    const h=setup({...options,query:'?td2edit=1#section'});h.row().children[0].events.click();await flush();assert.deepEqual(h.copied,['https://td2.huijiwiki.com/wiki/'+encodeURIComponent('威胁度')]);
  }
  for(const options of [{noClipboard:true},{writeText:()=>Promise.reject(Error('denied'))},{writeText:()=>{throw Error('unavailable');}}]){
    const failure=setup(options);failure.row().children[0].events.click();await flush();assert.equal(failure.row().children[0].textContent,'复制失败');assert.deepEqual(failure.copied,[]);
  }
});

test('form transport rechecks permission before save and sends no denied write',async()=>{
  const transport=require('../ui/editor/src/mediawiki-adapter');
  for(const deny of [r=>r.user.groups=['verified'],r=>r.user.rights=[],r=>r.page.actions.edit=false]) {
    let posts=0;
    const state={user:{id:1,name:'Admin',groups:['sysop'],rights:['edit']},page:{title:'品牌套装-5.11 Tactical',pageid:617,ns:0,actions:{edit:true}}};
    const api={get:async p=>({curtimestamp:'2026-11-16T12:00:00Z',query:{userinfo:state.user,pages:[{...state.page,
      ...(p.rvprop?{revisions:[{revid:2602,parentid:2601,timestamp:'2026-11-16T11:00:00Z',sha1:'test',slots:{main:{contentmodel:'wikitext',contentformat:'text/x-wiki',content:raw}}}]}:{})}]}}),
      post:async()=>{posts++;throw Error('unexpected write');}};
    const adapter=transport.create(api,{origin:transport.ORIGIN,target:state.page.title,pageid:617,contractPages:true,enableWrites:true});
    const base=await adapter.load();deny(state);
    await assert.rejects(adapter.save(base,raw+'\n'),/EDITOR_ACCESS_DENIED|EDIT_LOGIN_REQUIRED/);assert.equal(posts,0);
  }
});
