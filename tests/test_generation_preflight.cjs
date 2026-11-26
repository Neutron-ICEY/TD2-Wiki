'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),vm=require('node:vm'),{createRequire}=require('node:module');
const generated=require('../tools/generation.cjs'),root=path.resolve(__dirname,'..');
test('a dangling generated-target symlink is rejected even when existsSync is false',()=>{
 const file=path.join(root,'tools/generation.cjs'),entry={exports:{}},target=path.join(root,'wiki/templates/dangling.wiki');
 const mock={...fs,existsSync:p=>p===target?false:fs.existsSync(p),lstatSync(p){return p===target?{isSymbolicLink:()=>true}:fs.lstatSync(p);}};
 vm.runInNewContext(fs.readFileSync(file,'utf8'),{require:n=>n==='node:fs'?mock:require(n==='./naming.cjs'?'../tools/naming.cjs':n),module:entry,exports:entry.exports,Buffer});
 assert.throws(()=>entry.exports.targetPath(root,'wiki/templates/dangling.wiki'),/Symlink/);
});
test('late generated path, ownership and duplicate failures leave prior source untouched',()=>{
 const temp=fs.mkdtempSync(path.join(root,'dist/td2-generation-'));
 try{
  const first='wiki/templates/first.wiki',second='wiki/templates/second.wiki',sources={[first]:'updated',[second]:'new'};
  fs.mkdirSync(path.dirname(path.join(temp,first)),{recursive:true});fs.writeFileSync(path.join(temp,first),'original');
  const registry={entries:Object.keys(sources).map(source=>({source,title:'Template:'+path.basename(source),namespace:10,ownership:'generated',generator:'test'}))};
  for(const change of [r=>r.entries[1].ownership='manual',r=>r.entries.pop(),r=>r.entries.push({...r.entries[1]}),r=>r.entries[1].generator='wrong',r=>r.entries[1].title=r.entries[0].title]){
   const bad=structuredClone(registry);change(bad);
   assert.throws(()=>generated.apply(generated.plan(temp,sources,bad,'test')));
   assert.equal(fs.readFileSync(path.join(temp,first),'utf8'),'original');assert(!fs.existsSync(path.join(temp,second)));
  }
  assert.throws(()=>generated.apply(generated.plan(temp,{[first]:'updated',[second]:String.fromCharCode(0xd800)},registry,'test')),/invalid Unicode/);
  assert.equal(fs.readFileSync(path.join(temp,first),'utf8'),'original');assert(!fs.existsSync(path.join(temp,second)));
  fs.mkdirSync(path.join(temp,second));assert.throws(()=>generated.plan(temp,sources,registry,'test'),/target/);
  assert.equal(fs.readFileSync(path.join(temp,first),'utf8'),'original');
 }finally{assert(path.dirname(temp)===path.join(root,'dist'));fs.rmSync(temp,{recursive:true,force:true});}
});
for(const index of [1,2])for(const mutation of ['manual','missing','duplicate','wrong-generator'])test('exotic generation rejects late '+index+' '+mutation+' before all writes',()=>{
 const file=path.join(root,'tools/exotic_gear/generate.cjs'),real=createRequire(file),entry={exports:{}},writes=[];
 const registry=JSON.parse(fs.readFileSync(path.join(root,'publishing/registry.json'),'utf8'));
 const targets=['wiki/modules/TD2装备属性数据.lua','wiki/templates/奇特装备信息.wiki','wiki/templates/奇特装备属性槽.wiki'];
 const target=registry.entries.find(row=>row.source===targets[index]);
 if(mutation==='manual')target.ownership='manual';
 if(mutation==='missing')registry.entries.splice(registry.entries.indexOf(target),1);
 if(mutation==='duplicate')registry.entries.push({...target});
 if(mutation==='wrong-generator')target.generator='other';
 const mock={...fs,readFileSync(file,...args){return path.resolve(file)===path.join(root,'publishing/registry.json')?JSON.stringify(registry):fs.readFileSync(file,...args);},writeFileSync(...args){writes.push(args);}};
 function req(name){if(name==='node:fs')return mock;
  if(name==='./naming.cjs')return require('../tools/naming.cjs');if(name==='./data.cjs')return {readerData:()=> 'CHANGED TEST ONLY'};if(name==='../generation.cjs'){const shared={exports:{}};vm.runInNewContext(fs.readFileSync(path.join(root,'tools/generation.cjs'),'utf8'),{require:req,module:shared,exports:shared.exports,Buffer});return shared.exports;}return real(name);}req.main=entry;
 assert.throws(()=>vm.runInNewContext(fs.readFileSync(file,'utf8'),{require:req,module:entry,exports:entry.exports,__dirname:path.dirname(file),process:{argv:['node',file,'generate']},console}),/Generated ownership/);
 assert.deepEqual(writes,[]);
});
