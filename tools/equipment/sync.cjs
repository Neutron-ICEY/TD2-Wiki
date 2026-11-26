'use strict';
const fs=require('node:fs'),assert=require('node:assert/strict');
const page=require('./page.cjs'),{reconcile,key}=require('./merge.cjs');
function targets(raw){
  const result=[];
  function visit(node,records){
    for(const [field,entry] of Object.entries(node.fields)){
      const rows=entry.records,identities=rows.map(r=>{
        const f=r.fields;
        if(f.效果ID&&f.模式)return {效果ID:f.效果ID.value,模式:f.模式.value};
        for(const name of ['stable_id','装备UID','槽位ID'])if(f[name]?.value)return {[name]:f[name].value};
        return null;
      });
      if(rows.length&&identities.every(Boolean))rows.forEach((r,i)=>visit(r,[...records,{field,id:identities[i],template:r.template}]));
      else result.push({field,records});
    }
  }
  visit(page.read(raw).root,[]);return result;
}
function sync(base,local,remote){
  assert.equal(page.read(base).root.template,page.read(remote).root.template,'Remote template changed');
  const all=[...new Map([...targets(base),...targets(remote)].map(t=>[key(t),t])).values()];
  const result=reconcile(base,local,remote,all);
  const b=page.read(base).document,r=page.read(remote).document;
  let l=page.read(result.raw).document;
  for(const part of ['prefix','suffix'])if(r[part]!==b[part]&&r[part]!==l[part]){
    if(l[part]!==b[part])result.conflicts.push({field:part});
    else {result.raw=part==='prefix'?r.prefix+result.raw.slice(l.main.start):result.raw.slice(0,l.main.end)+r.suffix;l=page.read(result.raw).document;}
  }
  for(const target of all)if(page.value(page.read(base),target)!==undefined&&page.value(page.read(remote),target)===undefined)result.conflicts.push({target,reason:'Remote field or record removed'});
  if(result.conflicts.length)result.raw=local;
  return result;
}
if(require.main===module){
  const [base,local,remote,output]=process.argv.slice(2);assert(output,'Usage: sync.cjs confirmed-base.wiki local.wiki latest-remote.wiki new-output.wiki');assert(!fs.existsSync(output),'Use a new output file');
  const result=sync(...[base,local,remote].map(f=>fs.readFileSync(f,'utf8')));
  if(result.conflicts.length){console.error(JSON.stringify(result.conflicts,null,2));process.exitCode=1;}else{fs.writeFileSync(output,result.raw);console.log('Remote changes merged; source and confirmed base were not changed');}
}
module.exports={sync,targets};
