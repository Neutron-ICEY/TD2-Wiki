'use strict';
const parser=require('../../ui/editor/src/parser.js');
const source=require('../../ui/editor/src/source-patches.js');
const assert=require('node:assert/strict');
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
function read(raw){
  const document=parser.parse(raw,{textEnvelope:true});
  function node(ast){
    const fields={};
    let position=0;
    for(const s of ast.segments){
      const key=s.equal===null?String(++position):source.key(raw,s);assert(key&&!own(fields,key),'Duplicate parameter: '+key);
      fields[key]={value:raw.slice(s.equal===null?s.start:s.equal+1,s.end).trim(),segment:s,records:s.nested.map(node)};
    }
    return {template:ast.name,fields,ast};
  }
  return {raw,document,root:node(document.main)};
}
function find(page,steps){
  let node=page.root;
  for(const step of steps){
    const matches=(node.fields[step.field]?.records||[]).filter(r=>Object.entries(step.id).every(([key,value])=>r.fields[key]?.value===value));
    assert(matches.length<=1,'Ambiguous record identity: '+JSON.stringify(step));
    if(!matches.length)return null;node=matches[0];
  }
  return node;
}
function value(page,target){return find(page,target.records||[])?.fields[target.field]?.value;}
function record(template,fields){return '{{'+template+'\n'+Object.entries(fields).map(([k,v])=>'|'+k+'='+v+'\n').join('')+'}}';}
function update(raw,changes){
  let page=read(raw);
  for(const {target,value:next,template} of changes){
    assert(typeof next==='string','Imported value must be text');
    let node=page.root;
    for(const step of target.records||[]){
      let child=find({root:node},[step]);
      if(!child){
        assert(step.template||template,'New record needs its template');
        const collection=node.fields[step.field],item=record(step.template||template,step.id);
        const text=(collection?.value?collection.value+'\n':'')+item;
        const at=collection?.segment;
        raw=source.apply(raw,at?[{start:at.equal+1,end:at.end,text:text+'\n'}]:[{start:node.ast.end-2,end:node.ast.end-2,text:'|'+step.field+'='+text+'\n'}]);
        page=read(raw);node=find(page,(target.records||[]).slice(0,(target.records||[]).indexOf(step)+1));
      }else node=child;
    }
    const field=node.fields[target.field];
    if(field?.value===next)continue;
    if(field){
      const old=raw.slice(field.segment.equal+1,field.segment.end),lead=old.trim()?old.slice(0,old.length-old.trimStart().length):'',tail=old.slice(old.trimEnd().length);
      raw=source.apply(raw,[{start:field.segment.equal+1,end:field.segment.end,text:lead+next+tail}]);
    }else raw=source.apply(raw,[{start:node.ast.end-2,end:node.ast.end-2,text:'|'+target.field+'='+next+'\n'}]);
    page=read(raw);
  }
  for(const change of changes)assert.equal(value(page,change.target),change.value,'Imported field failed to reopen');
  return raw;
}
function remove(raw,keys){const page=read(raw);return source.apply(raw,keys.filter(k=>page.root.fields[k]).map(k=>{const s=page.root.fields[k].segment;return {start:s.start-1,end:s.end,text:''};}));}
module.exports={read,find,value,update,record,remove};
