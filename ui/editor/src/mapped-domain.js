(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./parser.js'),require('./source-patches.js'),require('./state.js'),require('./body-domain.js'),require('./text-boundary.js'),require('./page-fields.js'),()=>require('./equipment-inputs.cjs').equipment());
  else root.TD2EditorLab.mappedDomain=factory(root.TD2EditorLab.parser,root.TD2EditorLab.sourcePatches,root.TD2EditorLab.state,root.TD2EditorLab.body,root.TD2EditorLab.textBoundary,root.TD2EditorLab.pageFields,()=>({}));
}(typeof globalThis!=='undefined'?globalThis:this,function(parser,source,state,body,boundary,manual,defaults){
  const cell=value=>({type:'text',presence:value===null?'missing':value===''?'empty':'value',value});
  function create(raw,options={}){
    const data=options.equipmentCatalog?{catalog:options.equipmentCatalog}:defaults();
    const document=parser.parse(raw,{textEnvelope:true}),range=body.range(document);
    const identitySegment=document.main.segments.find(s=>source.key(raw,s)==='资料ID');
    const identity=identitySegment?raw.slice(identitySegment.equal+1,identitySegment.end).trim():null,entity=data.catalog[identity];
    const rules=manual.fields(document.main.name,entity);
    function read(text){
      const doc=parser.parse(text,{textEnvelope:true}),blockers=[];
      function fields(node,schema,path){
        const values=Object.fromEntries(Object.keys(schema).map(k=>[k,cell(null)])),seen=new Set();
        for(const s of node.segments){
          const key=source.key(text,s);
          if(seen.has(key)||!Object.hasOwn(schema,key)){blockers.push({path:path+'/'+key,code:seen.has(key)?'DUPLICATE_PARAMETER':'UNKNOWN_PARAMETER'});continue;}
          seen.add(key);values[key]=cell(text.slice(s.equal+1,s.end).trim());
        }
        return values;
      }
      const values=fields(doc.main,{资料ID:{},...rules},'equipment'),id=values.资料ID.value,entity=data.catalog[id];
      if(!entity||entity.template!==doc.main.name||id!==identity)blockers.push({path:'资料ID',code:'UNKNOWN_EQUIPMENT'});
      return {document:doc,blockers,state:{template:doc.main.name,fields:values,collections:{},body:body.range(doc).value}};
    }
    const baseline=read(raw);let current=state.clone(baseline.state),output=null;
    function validate(){
      const errors=[];
      function check(fields,schema,path){for(const [key,rule]of Object.entries(schema)){
        const value=fields[key]?.value||'';
        if(!boundary.valid(value.replace(/\r\n/g,'\n'),'wiki'))errors.push({path,field:key,message:'文本含不支持的结构'});
        if(rule.options&&!rule.options.includes(value))errors.push({path,field:key,message:'请选择有效选项'});
      }}
      check(current.fields,rules,'equipment');
      const message=current.body!==baseline.state.body&&body.validate(current.body);if(message)errors.push({path:'body',message});return errors;
    }
    function edit(key,value){
      if(!Object.hasOwn(rules,key))throw new Error('MAPPED_FIELD_READ_ONLY');
      const original=baseline.state.fields[key];
      current.fields[key]=value===''&&original.presence==='missing'?original:cell(value);
      output=null;
    }
    function matchesCatalog(nextEntity){
      if(!nextEntity||nextEntity.template!==document.main.name)return false;
      const updated=manual.fields(nextEntity.template,nextEntity);
      const keys=Object.keys(rules);
      return keys.length===Object.keys(updated).length&&keys.every(key=>Object.hasOwn(updated,key));
    }
    function serialize(){
      if(baseline.blockers.length)throw new Error('SAVE_BLOCKED');const errors=validate();if(errors.length)throw new Error(errors[0].message);
      const patches=source.create(document);
      for(const key of Object.keys(rules))if(!state.cellEqual(current.fields[key],baseline.state.fields[key]))patches.set(key,current.fields[key].value||'');
      if(current.body!==baseline.state.body){
        const {start,end,text}=body.replacement(document,range,current.body);
        patches.replace(start,end,text);
      }
      output=patches.finish(current,read,state.semanticEqual);return {raw:output,state:state.clone(current)};
    }
    return {isMapped:true,isGearSet:document.main.name==='装备组信息',isExoticGear:document.main.name==='奇特装备信息',identity,summary:entity,rules,
      get state(){return state.clone(current);},get blockers(){return baseline.blockers.slice();},get output(){return output;},bodyEnabled:options.allowBody===true,bodyRange:range,
      edit,editBody(value){if(!options.allowBody||!range.editable)throw new Error('BODY_READ_ONLY');current.body=value;output=null;},validate,serialize,matchesCatalog};
  }
  return {create};
}));
