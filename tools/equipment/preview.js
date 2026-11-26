(async function(){
  'use strict';
  const [samples,config]=await Promise.all([fetch('samples.json').then(r=>r.json()),fetch('config.json').then(r=>r.json())]);
  const labels=Object.fromEntries(Object.entries(samples).map(([key,value])=>[key,value.title]));
  const select=document.getElementById('sample'),reader=document.querySelector('.mw-parser-output');let current,instance,revision=1;
  for(const key of Object.keys(samples)){const o=document.createElement('option');o.value=key;o.textContent=labels[key];select.append(o);}
  async function parse(raw){const r=await fetch('/parse',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({raw})});if(!r.ok)throw new Error(await r.text());return r.json();}
  async function show(){
    document.getElementById('title').textContent=labels[select.value];reader.innerHTML=(await parse(current.raw)).html;reader.hidden=!!instance;
    document._td2BrandSetsRuntime.init(document);
  }
  async function choose(){if(instance){instance.dispose();instance=null;}current=samples[select.value];revision=1;await show();}
  select.addEventListener('change',choose);
  document.getElementById('edit').addEventListener('click',()=>{
    if(instance)return;reader.hidden=true;select.disabled=true;
    const base=()=>({title:current.title,pageid:1,revid:revision,raw:current.raw,userId:1,userName:'local-editor'});
    const adapter={load:async()=>base(),preview:parse,save:async(before,raw,onVerify)=>{
      if(before.revid!==revision||before.raw!==current.raw)throw new Error('editconflict');
      current.raw=raw;revision++;if(onVerify)onVerify();return {revision:base(),receipt:{local:true}};
    }};
    instance=TD2EditorLab.siteHost.mount({document,window,lab:TD2EditorLab,config,adapter,onExit:async()=>{instance=null;select.disabled=false;await show();}});
    window.td2Preview={get editor(){return instance;},get raw(){return current.raw;},parse};
  });
  document.getElementById('export').addEventListener('click',()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([current.raw],{type:'text/plain;charset=utf-8'}));a.download=select.value+'.wiki';a.click();URL.revokeObjectURL(a.href);});
  select.value=new URLSearchParams(location.search).get('sample')||'brand';await choose();
}());
