(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.TD2EditorLab.pageFields=factory();
}(typeof globalThis!=='undefined'?globalThis:this,function(){
  const note={type:'text',multiline:true};
  const talentKey=(id,mode)=>'天赋脚注:'+id+':'+mode;
  const label=name=>name.replace(/\{\{TD2文字\|色=[^|{}]+\|文=([^{}]*)\}\}/g,'$1').replace(/\s+/g,' ');
  function fields(template,entity){
    const talents=['装备组信息','奇特装备信息','武器信息'].includes(template)?entity?.talents||[]:[];
    return {...Object.fromEntries(talents.map(t=>[talentKey(t.id,t.mode),{...note,talentId:t.id,mode:t.mode,label:label(t.name)+' · '+t.mode}])),其他机制:note};
  }
  function isManual(key){return key==='其他机制'||key.startsWith('天赋脚注:');}
  return {fields,talentKey,isManual};
}));
