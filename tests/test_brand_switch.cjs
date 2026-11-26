/* 在轻量 DOM 中执行真实脚本；不冒充站点皮肤或 Page Forms。 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
class Element {
  constructor(className = "", tagName = "div") { this.body = this; this.className = className; this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = {}; this.events = {}; this.hidden = false; this.dataset = {}; this.nodeType = 1; this.parentElement = null; this.style = {values: {}, setProperty(key,value) {this.values[key]=value;}}; }
  get classList() { const self = this; return { contains(c) { return self.className.split(" ").includes(c); }, toggle(c, on) { self.className = self.className.split(" ").filter(x => x !== c).concat(on ? [c] : []).join(" "); } }; }
  get firstChild() { return this.children[0]; }
  appendChild(child) { if (child.parentElement) child.parentElement.removeChild(child); this.children.push(child); child.parentElement=this; }
  insertBefore(child, ref) { if (child.parentElement) child.parentElement.removeChild(child); const index = this.children.indexOf(ref); this.children.splice(index < 0 ? this.children.length : index, 0, child); child.parentElement=this; }
  removeChild(child) { this.children.splice(this.children.indexOf(child),1);child.parentElement=null; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  addEventListener(key, fn) { this.events[key] = fn; }
  focus() { this.focused = true; }
  matches(selector) { if(selector.includes(',')) return selector.split(',').some(s=>this.matches(s.trim())); return selector === "aside#toc.toc-sidebar" ? this.tagName === "ASIDE" && this.id === "toc" && this.classList.contains("toc-sidebar") : selector[0] === "." && this.classList.contains(selector.slice(1)); }
  querySelectorAll(selector) { return this.children.flatMap(x => ((selector === "aside#toc.toc-sidebar > .toc-ul-wrap" ? x.classList.contains("toc-ul-wrap") && x.parentElement.matches("aside#toc.toc-sidebar") : x.matches(selector)) ? [x] : []).concat(x.querySelectorAll(selector))); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getElementById(id) { return this.id === id ? this : this.children.map(child => child.getElementById(id)).find(Boolean) || null; }
  getClientRects() { for (let p=this;p;p=p.parentElement) if(p.hidden || p.visible===false) return []; return [{}]; }
}
const document = new Element(); document.readyState = "complete"; document.createElement = () => new Element();
const brand = new Element("td2-brand"); document.appendChild(brand);
const identity = new Element("td2-identity"); brand.appendChild(identity);
const equipment = new Element("td2-equipment"); document.appendChild(equipment);
for (const parent of [brand, equipment]) for (const mode of ["pve", "pvp"]) parent.appendChild(new Element("td2-brand-panel td2-brand-" + mode));
const source = fs.readFileSync(path.join(__dirname, "../ui/brand-sets/brand-sets.js"), "utf8");
vm.runInNewContext(source, { document });
assert.equal(typeof document._td2BrandSetsRuntime.initWeaponCharts, "function");
const controls = document.querySelector(".td2-brand-mode-controls");
assert.equal(document.querySelectorAll(".td2-brand-mode-controls").length, 1);
assert.equal(controls.getAttribute("data-mode"), "PvE");
assert.equal(controls.children[0].attributes["aria-pressed"], "true");
for (const panel of document.querySelectorAll(".td2-brand-panel")) assert.equal(panel.hidden, panel.classList.contains("td2-brand-pvp"));
controls.children[1].events.click();
assert.equal(controls.getAttribute("data-mode"), "PvP");
for (const panel of document.querySelectorAll(".td2-brand-panel")) {
 assert.equal(panel.hidden, panel.classList.contains("td2-brand-pve"));
 assert.equal(panel.classList.contains("td2-mode-pvp"), panel.classList.contains("td2-brand-pvp"));
}
assert.equal(identity.hidden, false);
// 重复初始化与新增动态内容仍复用页面状态。
equipment.appendChild(new Element("td2-brand-panel td2-brand-pve"));
vm.runInNewContext(source, { document });
assert.equal(document.querySelectorAll(".td2-brand-mode-controls").length, 1);
assert.equal(equipment.children.at(-1).hidden, true);
let prevented = false;
controls.children[1].events.keydown({ key: "ArrowLeft", preventDefault() { prevented = true; } });
assert.equal(prevented, true); assert.equal(controls.children[0].focused, true);
for (const panel of document.querySelectorAll(".td2-brand-panel")) assert.equal(panel.hidden, panel.classList.contains("td2-brand-pvp"));
// Sandbox-015：直接挂 body，不读取 TOC；退出/返回Reader保留单一状态。
const sideDoc=new Element();sideDoc.readyState="complete";sideDoc.documentElement=sideDoc;
sideDoc.createElement=tag=>new Element("",tag);
const sideBrand=new Element("td2-brand");sideDoc.appendChild(sideBrand);
for(const mode of ["pve","pvp"]) sideBrand.appendChild(new Element("td2-brand-panel td2-brand-"+mode));
let sideMutation;const sideHooks=[];
class SideObserver {constructor(cb){sideMutation=cb;} observe(){}}
const sideEnv={document:sideDoc,MutationObserver:SideObserver,mw:{hook(){return {add(cb){sideHooks.push(cb);}};}}};
vm.runInNewContext(source,sideEnv);
const bar=sideDoc.querySelector(".td2-brand-mode-controls");
assert.equal(bar.parentElement,sideDoc.body);assert.equal(bar.children.length,2);
assert.equal(bar.classList.contains("td2-surface"),false);
for(const button of bar.children){
 assert.equal(button.className,"td2-frame");
 const fragment=button.querySelector(".td2-frame-corners");
 assert.equal(fragment.getAttribute("aria-hidden"),"true");
 assert.equal(fragment.children.length,4);
 assert.deepEqual(fragment.children.map(n=>n.className),["nw","ne","sw","se"].map(c=>"td2-corner-node td2-corner-"+c));
}
const click=bar.children[1].events.click;click();
// 有/无、折叠/展开或高度改变的目录都不能重新挂载按钮。
const toc=new Element("toc-sidebar","aside");toc.id="toc";sideDoc.appendChild(toc);
for(const height of ["", "0px", "600px"]){
 toc.style.height=height;toc.visible=height!=="";
 sideDoc._td2BrandSetsRuntime.init(sideDoc);sideHooks[0]([sideBrand]);
 assert.equal(bar.parentElement,sideDoc.body);assert.equal(toc.children.length,0);
 assert.equal(bar.children[1].events.click,click);
 assert.equal(bar.getAttribute("data-mode"),"PvP");
}
vm.runInNewContext(source,sideEnv);
assert.equal(sideHooks.length,2);assert.equal(sideDoc.querySelectorAll(".td2-brand-mode-controls").length,1);
assert.equal(sideDoc.querySelectorAll(".td2-corner-node").length,8);
sideDoc.removeChild(sideBrand);sideMutation([{addedNodes:[],removedNodes:[sideBrand]}]);
assert.equal(sideDoc.querySelectorAll(".td2-brand-mode-controls").length,0);
sideDoc.appendChild(sideBrand);sideMutation([{addedNodes:[sideBrand],removedNodes:[]}]);
assert.equal(sideDoc.querySelector(".td2-brand-mode-controls"),bar);
assert.equal(bar.getAttribute("data-mode"),"PvP");
assert.equal(sideBrand.querySelector(".td2-brand-pve").hidden,true);
assert.equal(bar.parentElement, sideDoc.body);
assert.equal(toc.querySelectorAll(".td2-brand-mode-controls").length, 0);
console.log("Sandbox-015：body宿主、无目录依赖、8个共享角点、SPA单状态与监听幂等通过。");

// 主属性的父上下文现由服务端投影；客户端不再复制隐藏的类别正文。
assert.equal(source.includes("td2-brand-major-source"),false);
assert.equal(source.includes("cloneNode"),false);

// Sandbox-009：真实脚本在 ResourceLoader 相同的早/晚时机执行；不模拟站点联网。
let lifecycleChecks = 0;
for (const readyState of ["loading", "interactive", "complete"]) {
 const doc = new Element(); doc.readyState = readyState; doc.documentElement = doc;
 doc.createElement = () => new Element();
 const listeners = {}, hooks = [], mutations = []; let mutationCount = 0, intersectionCount = 0;
 doc.addEventListener = (name, callback) => { (listeners[name] ||= []).push(callback); };
 const root = new Element("td2-brand"); root.ownerDocument = doc; doc.appendChild(root);
 for (let i=0;i<3;i++) for (const mode of ["pve", "pvp"]) root.appendChild(new Element("td2-brand-panel td2-brand-"+mode));
 class ContentObserver { constructor(callback) { mutationCount++;mutations.push(callback); } observe() {} }
 class PositionObserver { constructor() { intersectionCount++; } observe() {} }
 const env = {document:doc,MutationObserver:ContentObserver,IntersectionObserver:PositionObserver,
   mw:{hook(name) { assert.equal(name,"wikipage.content"); return {add(callback) { hooks.push(callback); }}; }}};
 vm.runInNewContext(source,env);
 if(readyState === "loading") {
   assert.equal(doc.querySelectorAll(".td2-brand-mode-controls").length,0);
   assert.equal(listeners.DOMContentLoaded.length,2);
   doc.readyState="interactive";listeners.DOMContentLoaded.forEach(callback => callback());
 }
 const bar=doc.querySelector(".td2-brand-mode-controls");
 assert.ok(bar);assert.equal(bar.parentElement,doc.body);assert.equal(bar.getAttribute("data-mode"),"PvE");
 bar.children[1].events.click();
 const originalClick=bar.children[1].events.click, originalKey=bar.children[1].events.keydown;
 const runtime=doc._td2BrandSetsRuntime;
 const initCharts = runtime.initWeaponCharts;
 const chartScopes = [];
 runtime.initWeaponCharts = scope => { chartScopes.push(scope); initCharts(scope); };
 runtime.init(doc);hooks[0]([root]);hooks[0]([root]);
 assert.deepEqual(chartScopes, [doc, doc, doc]);
 vm.runInNewContext(source,env); // 重复 evaluate 也不得注册第二组 hook/观察器。
 assert.equal(doc._td2BrandSetsRuntime,runtime);
 assert.equal(hooks.length,2);assert.equal(mutationCount,1);assert.equal(intersectionCount,0);
 assert.equal(bar.children[1].events.click,originalClick);assert.equal(bar.children[1].events.keydown,originalKey);
 assert.equal(doc.querySelectorAll(".td2-brand-mode-controls").length,1);
 assert.equal(doc.querySelectorAll(".td2-brand-floating-controls").length,0);
 assert.equal(bar.getAttribute("data-mode"),"PvP");assert.equal(bar.children[1].getAttribute("aria-pressed"),"true");
 assert.equal((listeners.DOMContentLoaded || []).length,readyState==="loading" ? 2 : 0);
 const panel=new Element("td2-brand-panel td2-brand-pve");panel.nodeType=1;
 root.appendChild(panel);
 mutations[0]([{addedNodes:[panel]}]);
 assert.equal(panel.hidden,true);assert.equal(bar.getAttribute("data-mode"),"PvP");
 assert.equal(doc.querySelectorAll(".td2-brand-mode-controls").length,1);
 // 空 PvP 面板只是空 PvP；脚本不填充任何游戏数据。
 assert.equal(root.querySelector(".td2-brand-pvp").textContent,undefined);
 lifecycleChecks++;
}
// DOM 已 ready，但 Reader 在脚本之后才到达：由原观察器补初始化，默认仍 PvE。
const lateDoc=new Element();lateDoc.readyState="complete";lateDoc.documentElement=lateDoc;lateDoc.createElement=()=>new Element();
let lateNotify;
class LateObserver {constructor(callback) {lateNotify=callback;} observe() {}}
vm.runInNewContext(source,{document:lateDoc,MutationObserver:LateObserver});
assert.equal(lateDoc.querySelectorAll(".td2-brand-mode-controls").length,0);
const lateBrand=new Element("td2-brand");lateBrand.nodeType=1;
lateDoc.appendChild(lateBrand);
for (const mode of ["pve","pvp"]) lateBrand.appendChild(new Element("td2-brand-panel td2-brand-"+mode));
lateNotify([{addedNodes:[lateBrand]}]);
assert.equal(lateDoc.querySelector(".td2-brand-mode-controls").getAttribute("data-mode"),"PvE");
assert.equal(lateDoc.querySelectorAll(".td2-brand-mode-controls").length,1);
lifecycleChecks++;
console.log("Sandbox-009 Reader 生命周期场景通过："+lifecycleChecks+"（早加载、interactive晚加载、complete晚加载、晚到Reader）；hook/观察器/控件/监听幂等。");

// 已批准的正文左侧定位：宽屏靠近正文，窄屏回退；重复初始化不重绑。
let resizeCallback, observeCallback, resizeBindings=0, hashBindings=0, popstateBindings=0;
const positioned=new Element(); positioned.readyState="complete"; positioned.documentElement=positioned;
positioned.clientWidth=1440; positioned.createElement=()=>new Element();
positioned.defaultView={getComputedStyle(){return {paddingLeft:"12px"};},addEventListener(type,cb){if(type==='hashchange'){hashBindings++;return;}if(type==='popstate'){popstateBindings++;return;}assert.equal(type,"resize");resizeBindings++;resizeCallback=cb;}};
const positionedBrand=new Element("td2-brand"); let readerLeft=300;
positionedBrand.getBoundingClientRect=()=>({left:readerLeft}); positioned.appendChild(positionedBrand);
positionedBrand.appendChild(new Element("td2-brand-panel td2-brand-pve"));
const originalCreate=positioned.createElement;
positioned.createElement=()=>{const e=originalCreate();e.getBoundingClientRect=()=>({width:160});return e;};
class PositionObserver{constructor(cb){observeCallback=cb;}observe(){}disconnect(){}}
const positionEnv={document:positioned,ResizeObserver:PositionObserver};
vm.runInNewContext(source,positionEnv);
const positionedBar=positioned.querySelector(".td2-brand-mode-controls");
assert.equal(positionedBar.style.values["--td2-mode-offset"],"128px");
for(const width of [320,390]){positioned.clientWidth=width;readerLeft=16;resizeCallback();assert.equal(positionedBar.style.values["--td2-mode-offset"],"12px");}
positioned.clientWidth=1440;readerLeft=500;observeCallback();assert.equal(positionedBar.style.values["--td2-mode-offset"],"328px");
vm.runInNewContext(source,positionEnv);assert.equal(resizeBindings,1);assert.equal(hashBindings,1);assert.equal(popstateBindings,1);assert.equal(positioned.querySelectorAll(".td2-brand-mode-controls").length,1);
console.log("正文留白定位、320/390回退、布局变化及重复初始化通过。");

async function checkCopyFeedback() {
  const doc = new Element(); doc.readyState = "complete";
  doc.createElement = tag => new Element("", tag);
  doc.appendChild(new Element("td2-brand"));
  const heading = new Element(); heading.id = "firstHeading"; doc.appendChild(heading);
  const pending = [], timers = new Map(); let timerId = 0;
  vm.runInNewContext(source, {
    document: doc, URL, location: {href: "https://example.test/brand?mode=test#named-one"},
    navigator: {clipboard: {writeText(url) {
      assert.equal(url, "https://example.test/brand?mode=test");
      return new Promise((resolve, reject) => pending.push({resolve, reject}));
    }}},
    setTimeout(fn, delay) { assert.equal(delay, 1800); timers.set(++timerId, fn); return timerId; },
    clearTimeout(id) { timers.delete(id); }
  });
  const copy = doc.getElementById("td2-page-actions").children[0];
  const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
  const click = async () => { copy.events.click(); await flush(); };
  await click(); assert.equal(copy.textContent, "复制链接");
  pending.shift().resolve(); await flush();
  assert.equal(copy.textContent, "成功复制"); assert(copy.classList.contains("td2-copy-success"));
  assert.equal(timers.size, 1);
  await click(); assert.equal(timers.size, 0); assert.equal(copy.textContent, "复制链接");
  pending.shift().resolve(); await flush();
  assert.equal(copy.textContent, "成功复制"); assert.equal(timers.size, 1);
  const restore = [...timers.values()][0]; timers.clear(); restore();
  assert.equal(copy.textContent, "复制链接"); assert(!copy.classList.contains("td2-copy-success"));
  await click(); const older = pending.shift();
  await click(); pending.shift().reject(new Error("denied")); await flush();
  assert.equal(copy.textContent, "复制失败");
  older.resolve(); await flush();
  assert.equal(copy.textContent, "复制失败"); assert(!copy.classList.contains("td2-copy-success"));
  assert.equal(timers.size, 1);
  await click(); const failedOlder = pending.shift();
  await click(); pending.shift().resolve(); await flush();
  failedOlder.reject(new Error("late failure")); await flush();
  assert.equal(copy.textContent, "成功复制"); assert.equal(timers.size, 1);
  console.log("复制反馈通过：成功、失败、1800ms恢复、连续点击、异步乱序与URL去锚点。");
}
checkCopyFeedback().catch(error => { console.error(error); process.exitCode = 1; });

