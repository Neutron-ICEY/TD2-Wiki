(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.TD2EditorLab.equipmentAttributes=factory();
}(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const units={percent:'%',number:'',seconds:'秒'},own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
  function project(data,minor,presets,shared){
    if(data.schema_version!==1)throw new Error('ATTRIBUTE_SCHEMA');
    const identities=new Map([...minor.attributes,...data.core_attributes].map(a=>{const n=data.identities?.[a.id];return [a.id,n?{...a,zh_name:n.display_alias||n.zh_name,en_name:n.en_name,unit_type:n.unit_type}:a];})),seen=new Set();
    const rows=data.rules.map(r=>{
      if(!['ordinary','core','exotic_special'].includes(r.kind)||!identities.has(r.attribute_id)||seen.has(r.id)||!Array.isArray(r.evidence)||!r.evidence.length)throw new Error('ATTRIBUTE_RULE');
      seen.add(r.id);const a=identities.get(r.attribute_id);
      if(r.kind==='ordinary'&&!/^ordinary_minor_[a-z0-9_]+$/.test(r.id)||r.kind==='core'&&!/^core_[a-z0-9_]+$/.test(r.id)||r.kind==='exotic_special'&&!/^exotic_minor_[a-z0-9_]+$/.test(r.id))throw new Error('ATTRIBUTE_DOMAIN');
      if(!own(units,a.unit_type))throw new Error('ATTRIBUTE_UNIT');
      const core=r.kind==='core',display=core&&shared?.base.major_display_values[r.core_type];
      if(core&&(!display||!shared.ui.major_names[r.core_type]||own(r,'display_max')))throw new Error('CORE_ATTRIBUTE_SOURCE');
      const maximum=core?display.replace(/[, %]/g,''):r.display_max;
      if(maximum!==null&&!/^\d+(?:\.\d+)?$/.test(maximum))throw new Error('ATTRIBUTE_VALUE');
      return {...r,display_max:maximum,...(core?{display_value:display}:{}),zh_name:a.zh_name,en_name:a.en_name,category:a.category,unit:a.unit_type,active:a.active!==false};
    });
    for(const p of presets.presets){
      const a=identities.get(p.minor_attribute_id);
      if(!a||seen.has(p.id)||!/^fixed_minor_[a-z0-9_]+$/.test(p.id))throw new Error('SPECIAL_ATTRIBUTE_ID');
      seen.add(p.id);rows.push({...p,attribute_id:p.minor_attribute_id,display_max:p.value,kind:'named_special',zh_name:a.zh_name,en_name:a.en_name,category:a.category,unit:a.unit_type});
    }
    rows.sort((a,b)=>Number(a.kind==='exotic_special')-Number(b.kind==='exotic_special'));
    const pools=data.pools.map(p=>{
      if(!/^pool_[a-z0-9_]+$/.test(p.id)||!Array.isArray(p.rules)||!p.rules.length||new Set(p.rules).size!==p.rules.length||p.rules.some(id=>!rows.some(r=>r.id===id&&r.kind===p.kind)))throw new Error('ATTRIBUTE_POOL');
      return {...p};
    });
    if(new Set(pools.map(p=>p.id)).size!==pools.length)throw new Error('ATTRIBUTE_POOL_ID');
    return {rules:rows,pools};
  }
  function resolve(data,id){const r=data.rules.find(r=>r.id===id);if(!r)throw new Error('UNKNOWN_ATTRIBUTE_RULE');return r;}
  function label(r){return r.zh_name+(r.display_max===null?'':' · '+(r.display_value||r.display_max+units[r.unit]));}
  function value(r,percent=''){
    if(r.display_max===null)return r.zh_name+'（数值待核实）';
    const number=Number(percent);
    if(percent!==''&&number!==-1&&number!==100&&r.kind!=='named_special')return r.zh_name+'（数值待核实）';
    return (r.display_value||r.display_max+units[r.unit])+' '+r.zh_name;
  }
  return {project,resolve,label,value,units};
}));
