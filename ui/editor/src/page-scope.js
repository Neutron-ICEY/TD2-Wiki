(function(root,factory){
 if(typeof module==='object'&&module.exports)module.exports=factory(require('./parser.js'));
 else (root.TD2EditorLab=root.TD2EditorLab||{}).pageScope=factory(root.TD2EditorLab.parser);
}(typeof globalThis!=='undefined'?globalThis:this,function(parser){
 'use strict';
 const template='品牌套装信息',templates=parser.MAIN_TEMPLATES;
 function check(raw,pageid){
  try{
   const doc=parser.parse(raw,{textEnvelope:true});
   const withoutComments=s=>s.replace(/<!--[\s\S]*?-->/g,'');
   if(withoutComments(doc.prefix).trim())return {ok:false,reason:'NOT_STANDALONE_BRAND_DATA'};
   const suffix=withoutComments(doc.suffix);
   if(suffix.includes('{{'))return {ok:false,reason:'AGGREGATE_OR_AUXILIARY_TEMPLATE'};
   const names=doc.main.segments.filter(s=>s.equal!==null).map(s=>raw.slice(s.start,s.equal).trim());
   if(names.includes('资料ID'))return {ok:true,template:doc.main.name};
   return {ok:false,reason:'INCOMPLETE_EQUIPMENT_IDENTITY'};
  }catch(e){return {ok:false,reason:e.code||e.message};}
 }
 return {template,templates,check};
}));
