(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory;
  else root.TD2EditorLab.mappedUI={create:factory};
}(typeof globalThis!=='undefined'?globalThis:this,function({document,container,session,onChange,api}){
  container.replaceChildren();const ui=api.uiPrimitives.create(document),fields=[],rules=session.rules;
  const labels={其他机制:'其他资料'};
  function el(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
  function section(title){const node=el('section');node.className='editor-section';node.append(el('h2',title));container.append(node);return node;}
  function group(parent,schema,get,edit,id){
    for(const [key,rule]of Object.entries(schema)){
      const input=el(rule.multiline?'textarea':'input');if(rule.multiline)input.rows=3;
      input.value=get(key);input.dataset.field=key;
      const field=ui.Field({id:id+'-'+key,label:rule.label||labels[key]||key,control:input});
      if(labels[key]==='其他资料')field.element.querySelector('label').classList.add('visually-hidden');
      parent.append(field.element);fields.push({path:id,key,field});
      input.addEventListener('input',()=>{edit(key,input.value);onChange();});
    }
  }
  const get=key=>session.state.fields[key]?.value||'';
  const talents=Object.fromEntries(Object.entries(rules).filter(([,rule])=>rule.talentId));
  const other=Object.fromEntries(Object.entries(rules).filter(([,rule])=>!rule.talentId));
  if(Object.keys(talents).length)group(section('天赋脚注'),talents,get,session.edit,'equipment');
  if(Object.keys(other).length)group(section('其他资料'),other,get,session.edit,'equipment');
  if(session.bodyEnabled&&session.bodyRange.editable){const parent=section('补充正文'),input=el('textarea');input.rows=6;input.value=session.state.body;const field=ui.Field({id:'equipment-body',label:'补充正文',control:input});field.element.querySelector('label').classList.add('visually-hidden');parent.append(field.element);fields.push({path:'body',field});input.addEventListener('input',()=>{session.editBody(input.value);onChange();});}
  const error=ui.Error('','equipment-errors');container.prepend(error.element);
  return {validate(){const errors=session.validate();for(const entry of fields)entry.field.setError(errors.find(e=>e.path===entry.path&&e.field===entry.key)?.message||'');error.setText([...new Set(errors.map(e=>e.message))].join('；'));return !errors.length;}};
}));
