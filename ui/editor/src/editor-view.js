(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory;
  else root.TD2EditorLab.editorView={create:factory};
}(typeof globalThis!=='undefined'?globalThis:this,function(options){
  return options.api.mappedUI.create(options);
}));
