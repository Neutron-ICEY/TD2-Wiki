(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.TD2EditorLab.sourcePatches=factory();
}(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const key=(raw,segment)=>segment.equal===null?'':raw.slice(segment.start,segment.equal).trim();
  const parameters=(raw,node,name)=>node.segments.filter(segment=>segment.equal!==null&&key(raw,segment)===name);
  const parameter=(raw,node,name)=>parameters(raw,node,name)[0];
  function apply(raw,patches){
    const sorted=patches.slice().sort((a,b)=>a.start-b.start||a.end-b.end);
    let end=-1;
    for(const patch of sorted){
      if(!Number.isInteger(patch.start)||!Number.isInteger(patch.end)||patch.start<0||patch.end<patch.start||patch.end>raw.length||typeof patch.text!=='string')throw new Error('INVALID_SOURCE_PATCH');
      if(patch.start<end)throw new Error('OVERLAPPING_SOURCE_PATCHES');
      end=patch.end;
    }
    let output=raw;
    for(const patch of sorted.reverse())output=output.slice(0,patch.start)+patch.text+output.slice(patch.end);
    return output;
  }
  function create(document){
    const raw=document.raw,patches=[],insertions=[];
    function set(name,value){
      const segment=parameter(raw,document.main,name);
      if(segment)patches.push({start:segment.equal+1,end:segment.end,text:value+'\n'});
      else insertions.push('|'+name+'='+value+'\n');
    }
    function remove(name){
      const segment=parameter(raw,document.main,name);
      if(segment)patches.push({start:segment.start-1,end:segment.end,text:''});
    }
    function replace(start,end,text){patches.push({start,end,text});}
    function finish(expected,read,equal){
      const all=patches.slice();
      if(insertions.length)all.push({start:document.main.end-2,end:document.main.end-2,text:insertions.join('')});
      const candidate=apply(raw,all),reopened=read(candidate);
      if(reopened.blockers.length||!equal(expected,reopened.state))throw new Error('LOCAL_REOPEN_FAILED');
      return candidate;
    }
    return {set,remove,replace,finish};
  }
  return {key,parameters,parameter,apply,create};
}));
