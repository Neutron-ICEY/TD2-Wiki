'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{createRequire}=require('node:module');
const root=path.resolve(__dirname,'..');
test('late template ownership failure performs zero generated writes',()=>{
  const file=path.join(root,'tools/gear_sets/generate.cjs'),real=createRequire(file),entry={exports:{}},writes=[];
  const mock={...fs,readFileSync(target,...args){if(path.resolve(target)===path.join(root,'publishing/registry.json')){const r=JSON.parse(fs.readFileSync(target,'utf8'));r.entries.find(e=>e.source==='wiki/templates/装备组信息.wiki').ownership='manual';return JSON.stringify(r);}return fs.readFileSync(target,...args);},writeFileSync(...args){writes.push(args);}};
  function req(name){return name==='node:fs'?mock:real(name);}req.main=entry;
  assert.throws(()=>vm.runInNewContext(fs.readFileSync(file,'utf8'),{require:req,module:entry,exports:entry.exports,__dirname:path.dirname(file),process:{argv:['node',file,'templates']},console}),/Generated ownership required/);
  assert.deepEqual(writes,[]);
});
test('approved core footnote remains independent of central text through edits',()=>{
  const gear=require('../ui/editor/src/mapped-domain.js');
  const raw=fs.readFileSync(path.join(root,'wiki/pages/gear-sets/装备组-烈焰大炮.wiki'),'utf8'),s=gear.create(raw),note='从第4次连续爆头开始，只有该次爆头击杀目标，才会同时获得三项奖励。';
  assert.deepEqual(s.blockers,[]);s.edit('天赋脚注:gear_effect:p_6cfec5e66374fe9f0003656879110b57:PvE',note);s.edit('其他机制','LOCAL TEST');
  const reopened=gear.create(s.serialize().raw);assert.equal(reopened.state.fields['天赋脚注:gear_effect:p_6cfec5e66374fe9f0003656879110b57:PvE'].value,note);assert.deepEqual(reopened.summary,s.summary);
  s.edit('天赋脚注:gear_effect:p_6cfec5e66374fe9f0003656879110b57:PvE','<script>bad</script>');assert.throws(()=>s.serialize(),/不支持/);
});
test('Navbox cycle keeps forward speed and both holds then returns continuously',()=>{
  const source=fs.readFileSync(path.join(root,'ui/brand-sets/brand-sets.js'),'utf8');
  const segment=source.slice(source.indexOf('var travel = distance / 22'),source.indexOf('\n        }',source.indexOf('var travel = distance / 22')));
  let frames,options;vm.runInNewContext(segment,{distance:110,entry:{text:{animate:(f,o)=>{frames=f;options=o;return {};}}}});
  assert.equal(options.duration,8300);assert.equal(frames[0].transform,frames.at(-1).transform);
  assert.equal(frames[1].offset*options.duration,1500);
  assert.equal(Math.round((frames[2].offset-frames[1].offset)*options.duration),5000);
  assert.equal(Math.round((frames[3].offset-frames[2].offset)*options.duration),1500);
  assert.equal(Math.round((1-frames[3].offset)*options.duration),300);
  assert.equal(frames[3].easing,'ease-in-out');assert.equal(options.easing,'linear');
});
test('formal build version changes for recipe-only changes and records lock',()=>{
  const file=path.resolve(root,'ui/editor/production/build.cjs'),real=createRequire(file),source=fs.readFileSync(file,'utf8');
  function build(extra){const outputs=new Map(),out=path.join(root,'dist/virtual-build-test');const mock={...fs,existsSync:f=>String(f)===out?false:fs.existsSync(f),readFileSync(f,...a){const raw=fs.readFileSync(f,...a);return path.resolve(f)===file?Buffer.from(raw.toString()+extra):raw;},mkdirSync(){},writeFileSync:(f,v)=>outputs.set(path.basename(f),v)};
    const req=n=>n==='fs'?mock:real(n);req.resolve=real.resolve;
    vm.runInNewContext(source,{require:req,__dirname:path.dirname(file),__filename:file,process:{argv:['node',file,out],versions:process.versions},console:{log(){}}});return JSON.parse(outputs.get('manifest.json'));}
  const a=build(''),b=build('\n');assert.notEqual(a.version,b.version);assert(a.inputs.some(r=>r.source.endsWith('/production/build.cjs')));assert(a.inputs.some(r=>r.source.endsWith('/tooling/package-lock.json')));assert.equal(a.toolchain.node,process.versions.node);
});
