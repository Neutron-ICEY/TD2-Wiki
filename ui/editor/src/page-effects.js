(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory(require('./parser.js'),require('./text-boundary.js'));
  else root.TD2EditorLab.pageEffects=factory(root.TD2EditorLab.parser,root.TD2EditorLab.textBoundary);
}(typeof globalThis!=='undefined'?globalThis:this,function(parser,boundary){
  'use strict';
  const key='效果资料',template='装备效果';
  const mappedFields=['名称','图标','属性ID','属性','数值','单位','描述'];
  const fields=['效果ID','模式','引用','所属装备','件数','部位','依赖',...mappedFields];
  function read(text){
    if(!text)return [];
    const raw='{{品牌套装信息\n|'+key+'='+text+'\n}}',doc=parser.parse(raw,{textEnvelope:true}),segment=doc.main.segments[0];
    let end=segment.equal+1;
    const rows=segment.nested.map(node=>{
      if(node.name!==template||raw.slice(end,node.start).trim())throw new Error('效果记录格式无效');end=node.end;
      const record={};
      for(const s of node.segments){const name=raw.slice(s.start,s.equal).trim();if(s.equal===null||!fields.includes(name)||Object.hasOwn(record,name))throw new Error('效果字段无效或重复');record[name]=raw.slice(s.equal+1,s.end).trim();}
      return record;
    });
    if(raw.slice(end,segment.end).trim())throw new Error('效果记录格式无效');
    const identities=new Set();
    for(const row of rows){
      const id=row.效果ID+'/'+row.模式;
      if(!row.效果ID||!['PvE','PvP'].includes(row.模式)||identities.has(id))throw new Error('效果 ID 与模式须唯一');identities.add(id);
      if(row.件数&&!/^[1-9]\d*$/.test(row.件数))throw new Error('件数须为正整数');
      if(row.数值&&!/^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(row.数值))throw new Error('效果数值格式无效');
      if(row.部位&&!['mask','backpack','chest','gloves','holster','kneepads'].includes(row.部位))throw new Error('装备部位无效');
      if(Object.values(row).some(v=>!boundary.valid(v,'wiki')))throw new Error('效果内容包含不支持的结构');
    }
    for(const row of rows)for(const id of (row.依赖||'').split(';').filter(Boolean))if(!rows.some(r=>r.效果ID===id&&r.模式===row.模式))throw new Error('效果依赖不存在');
    return rows;
  }
  function write(rows){const text=rows.map(row=>'{{'+template+'\n'+fields.filter(k=>row[k]!==undefined&&row[k]!=='').map(k=>'|'+k+'='+row[k]+'\n').join('')+'}}').join('\n');read(text);return text;}
  function resolve(rows,catalog=[]){return rows.map(row=>({...catalog.find(r=>r.id===row.引用)?.modes[row.模式],...row}));}
  return {key,template,fields,mappedFields,read,write,resolve};
}));
