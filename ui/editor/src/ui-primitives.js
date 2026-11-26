(function(root,factory){
  if(typeof module==="object" && module.exports)module.exports=factory();
  else {root.TD2EditorLab=root.TD2EditorLab||{};root.TD2EditorLab.uiPrimitives=factory();}
}(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  function create(document){
    function message(kind,text,id){
      const element=document.createElement("p");element.className=kind;
      if(id)element.id=id;
      if(kind==="error"){element.setAttribute("role","alert");element.setAttribute("aria-atomic","true");}
      function setText(value){
        element.replaceChildren();element.hidden=!value;
        if(value){const prefix=document.createElement("strong");prefix.textContent={help:"说明：",warning:"注意：",error:"错误："}[kind];element.append(prefix,document.createTextNode(value));}
      }
      setText(text);return {element,setText};
    }
    function Help(text,id){return message("help",text,id);}
    function Warning(text,id){return message("warning",text,id);}
    function Error(text,id){return message("error",text,id);}
    function Field({id,label,control,help="",warning=""}){
      if(!id || !label || !control || control.id && control.id!==id)throw new TypeError("FIELD_ID_LABEL_CONTROL_REQUIRED");
      const element=document.createElement("div"),labelElement=document.createElement("label");
      element.className="field";control.id=id;labelElement.htmlFor=id;labelElement.textContent=label;
      const helpMessage=Help(help,id+"-help"),warningMessage=Warning(warning,id+"-warning"),errorMessage=Error("",id+"-error");
      const originalDescriptions=(control.getAttribute("aria-describedby")||"").split(/\s+/).filter(Boolean);
      element.append(labelElement,control,helpMessage.element,warningMessage.element,errorMessage.element);
      function describe(){
        const ids=originalDescriptions.concat([helpMessage,warningMessage,errorMessage].filter(item=>!item.element.hidden).map(item=>item.element.id));
        if(ids.length)control.setAttribute("aria-describedby",Array.from(new Set(ids)).join(" "));else control.removeAttribute("aria-describedby");
      }
      function setError(text){errorMessage.setText(text);control.setAttribute("aria-invalid",String(Boolean(text)));describe();}
      setError("");
      return {element,control,setError,
        setHelp(text){helpMessage.setText(text);describe();},
        setWarning(text){warningMessage.setText(text);describe();}};
    }
    // Hidden content retains values and disabled states. Domain validation/serialization
    // must use explicit state, never infer storage semantics from DOM visibility.
    function ConditionalSection({element,visible=false,focusTarget}){
      function setVisible(value){
        const show=Boolean(value);
        if(!show && element.contains(document.activeElement)){
          if(focusTarget && !element.contains(focusTarget))focusTarget.focus();
          if(element.contains(document.activeElement))document.activeElement.blur();
        }
        element.hidden=!show;element.inert=!show;
      }
      setVisible(visible);return {element,setVisible,get visible(){return !element.hidden;}};
    }
    function ReferenceList({id,label,choices,getSelected,setSelected,addLabel,removeLabel,unknownLabel,unknownRemovable=false,allowDuplicates=false,allowReorder=false,canAdd=()=>true,onChange}){
      const select=document.createElement('select'),list=document.createElement('div'),actions=document.createElement('div'),add=document.createElement('button');
      select.dataset.editorTransient='true';
      const field=Field({id,label,control:select});
      list.className='reference-list';actions.className='collection-actions';
      add.type='button';add.textContent=addLabel;actions.append(add);
      field.element.insertBefore(list,select);field.element.append(actions);field.element.classList.add('reference-field');
      function commit(ids,action){setSelected(ids,action);refresh();onChange();}
      function focus(){(select.hidden?list.querySelector('button:not(:disabled)'):select)?.focus();}
      function refresh(){
        const ids=getSelected();list.replaceChildren();select.replaceChildren();
        const empty=document.createElement('option');empty.value='';empty.textContent='请选择……';select.append(empty);
        const groups=new Map();
        for(const choice of choices){
          if(choice.selectable===false||!allowDuplicates&&ids.includes(choice.id))continue;
          let parent=select;
          if(choice.group){
            if(!groups.has(choice.group)){const group=document.createElement('optgroup');group.label=choice.group;groups.set(choice.group,group);select.append(group);}
            parent=groups.get(choice.group);
          }
          const option=document.createElement('option');option.value=choice.id;option.textContent=choice.label;parent.append(option);
        }
        ids.forEach((id,index)=>{
          const choice=choices.find(row=>row.id===id),row=document.createElement('div'),text=document.createElement('span');
          row.className='reference-row';text.textContent=choice?choice.label:unknownLabel;row.append(text);
          if(allowReorder&&ids.length>1)for(const [delta,label] of [[-1,'上移'],[1,'下移']]){
            const move=document.createElement('button');move.type='button';move.textContent=label;move.setAttribute('aria-label',label+'：'+text.textContent);
            move.disabled=index+delta<0||index+delta>=ids.length;
            move.addEventListener('click',()=>{const next=ids.slice(),to=index+delta;if(to<0||to>=ids.length)return;next.splice(to,0,next.splice(index,1)[0]);commit(next,{type:'move',from:index,to});focus();});row.append(move);
          }
          if(choice?choice.removable!==false:unknownRemovable){
            const remove=document.createElement('button');remove.type='button';remove.textContent=removeLabel;
            remove.setAttribute('aria-label',removeLabel+'：'+text.textContent);
            remove.addEventListener('click',()=>{commit(ids.filter((_,i)=>i!==index),{type:'remove',index});focus();});row.append(remove);
          }
          list.append(row);
        });
        select.disabled=!canAdd()||!choices.some(choice=>choice.selectable!==false&&(allowDuplicates||!ids.includes(choice.id)));add.disabled=true;
        select.hidden=select.disabled;actions.hidden=select.disabled;
      }
      select.addEventListener('change',()=>{add.disabled=!select.value||!canAdd();});
      add.addEventListener('click',()=>{
        const choice=choices.find(row=>row.id===select.value&&row.selectable!==false),ids=getSelected();
        if(choice&&canAdd()&&(allowDuplicates||!ids.includes(choice.id))){commit(ids.concat(choice.id),{type:'add',id:choice.id});focus();}
      });
      refresh();return {...field,refresh,focus};
    }
    return {Field,Help,Warning,Error,ConditionalSection,ReferenceList};
  }
  return {create};
}));
