(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./mapped-domain.js'));
  else root.TD2EditorLab.localSession=factory(root.TD2EditorLab.mappedDomain);
}(typeof globalThis!=='undefined'?globalThis:this,function(mapped){
  return {create:(raw,catalog,options={})=>mapped.create(raw,options)};
}));
