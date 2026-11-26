'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
function titleKey(row){
  assert(Number.isSafeInteger(row.namespace)&&row.namespace>=0&&typeof row.title==='string'&&row.title&&row.title.trim()===row.title&&!/[\x00-\x1f\x7f#<>\[\]{}|]/.test(row.title),'Invalid generated Wiki target');
  const name=row.namespace?row.title.slice(row.title.indexOf(':')+1):row.title;
  return row.namespace+':'+require('./naming.cjs').normalized(name);
}
function targetPath(root,source){
  assert(typeof source==='string'&&source&&!/[\\:]/.test(source)&&!source.split('/').some(p=>!p||p==='.'||p==='..'||p.startsWith('.')),'Invalid generated source');
  require('./naming.cjs').safeRelative(source);
  root=path.resolve(root);const target=path.resolve(root,source),relative=path.relative(root,target);
  assert(relative&&!relative.startsWith('..')&&!path.isAbsolute(relative),'Generated target outside workspace');
  for(let current=target;current!==root;current=path.dirname(current)){
    let stat;try{stat=fs.lstatSync(current);}catch(error){if(error.code!=='ENOENT')throw error;}
    if(stat){
      assert(!stat.isSymbolicLink(),'Symlink generated target');
      assert(current===target?stat.isFile():stat.isDirectory(),'Invalid generated target or parent');
    }
  }
  return target;
}
function plan(root,sources,registry,generator){
  const seen=new Set();
  return Object.entries(sources).map(([source,text])=>{
    const rows=registry.entries.filter(row=>row.source===source);
    assert(rows.length===1&&rows[0].ownership==='generated'&&rows[0].generator===generator,'Generated ownership required: '+source);
    const identity=titleKey(rows[0]);assert.equal(registry.entries.filter(row=>titleKey(row)===identity).length,1,'Duplicate generated Wiki target');
    const target=targetPath(root,source),key=target.toLowerCase();assert(!seen.has(key),'Duplicate generated target');seen.add(key);
    assert(typeof text==='string','Generated text required');const bytes=Buffer.from(text,'utf8');
    assert.equal(bytes.toString('utf8'),text,'Generated text contains invalid Unicode');
    return {source,target,bytes,changed:!fs.existsSync(target)||!fs.readFileSync(target).equals(bytes)};
  });
}
function apply(batch,check=false){
  if(check)assert(batch.every(row=>!row.changed),'Generated sources are stale');
  else for(const row of batch)if(row.changed){fs.mkdirSync(path.dirname(row.target),{recursive:true});fs.writeFileSync(row.target,row.bytes);}
  return batch.filter(row=>row.changed).map(row=>row.source);
}
module.exports={targetPath,plan,apply};
