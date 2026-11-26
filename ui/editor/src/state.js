(function(root,factory){
  if(typeof module==="object" && module.exports) module.exports=factory();
  else root.TD2EditorLab.state=factory();
}(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  function cellEqual(a,b){
    if(!a || !b || a.presence!==b.presence || a.type!==b.type)return false;
    return a.value===b.value;
  }
  function recordEqual(a,b){
    if(a.template!==b.template || a.domain!==b.domain)return false;
    const keys=Object.keys(a.fields);
    if(keys.length!==Object.keys(b.fields).length)return false;
    return keys.every(k=>cellEqual(a.fields[k],b.fields[k]));
  }
  function semanticEqual(a,b){
    if(a.template!==b.template || a.body!==b.body)return false;
    if(Object.keys(a.fields).length!==Object.keys(b.fields).length || !Object.keys(a.fields).every(k=>cellEqual(a.fields[k],b.fields[k])))return false;
    const keys=Object.keys(a.collections);
    if(keys.length!==Object.keys(b.collections).length)return false;
    return keys.every(k=>{
      const x=a.collections[k],y=b.collections[k];
      return y && x.presence===y.presence && x.records.length===y.records.length && x.records.every((r,i)=>recordEqual(r,y.records[i]));
    });
  }
  function clone(state){return JSON.parse(JSON.stringify(state));}
  return {cellEqual,semanticEqual,clone};
}));
