'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..'),file=path.join(root,'tools/gear_sets/generate.cjs'),real=createRequire(file);
for(const mutation of ['none','content','ownership'])test('gear check validates '+mutation+' without writing maintained sources',()=>{
 const entry={exports:{}},writes=[],registryPath=path.join(root,'publishing/registry.json'),target=path.join(root,'wiki/modules/TD2装备组投影.lua');
 const mock={...fs,readFileSync(filename,...args){
  const value=fs.readFileSync(filename,...args);
  if(mutation==='content'&&path.resolve(filename)===target)return Buffer.from('NON-GAME-FACT stale source');
  if(mutation==='ownership'&&path.resolve(filename)===registryPath){
   const registry=JSON.parse(value);registry.entries.find(row=>row.source==='wiki/modules/TD2装备组投影.lua').ownership='manual';
   return JSON.stringify(registry);
  }
  return value;
 },writeFileSync(...args){writes.push(args);},mkdirSync(...args){writes.push(args);}};
 function req(name){
  if(name==='node:fs')return mock;
  if(name==='./naming.cjs')return require('../tools/naming.cjs');
  if(name==='../generation.cjs'){
   const shared={exports:{}};
   vm.runInNewContext(fs.readFileSync(path.join(root,'tools/generation.cjs'),'utf8'),{require:req,module:shared,exports:shared.exports,Buffer});
   return shared.exports;
  }
  return real(name);
 }
 req.main=entry;
 const run=()=>vm.runInNewContext(fs.readFileSync(file,'utf8'),{require:req,module:entry,exports:entry.exports,__dirname:path.dirname(file),process:{argv:['node',file,'check']},console,Buffer});
 if(mutation==='none')run();
 else assert.throws(run,mutation==='content'?/Generated sources are stale/:/Generated ownership required/);
 assert.deepEqual(writes,[]);
});
