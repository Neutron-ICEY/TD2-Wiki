'use strict';
const fs=require('node:fs'),path=require('node:path');
function references(root){return require('./database.cjs').references(require('./database.cjs').load(root));}
function data(root=path.resolve(__dirname,'../..'),records=require('./database.cjs').load(root)){
  return {catalog:[],options:{allowBody:true,equipmentCatalog:require('./projection.cjs').editor(records)}};
}
function lua(value){
  if(value===null||value===undefined)return 'nil';
  if(typeof value==='string')return '"'+value.replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/[\x00-\x1f\x7f]/g,c=>'\\'+c.charCodeAt(0).toString().padStart(3,'0'))+'"';
  if(typeof value!=='object')return String(value);
  return '{ '+(Array.isArray(value)?value.map(lua):Object.entries(value).map(([k,v])=>'['+lua(k)+']='+lua(v))).join(',')+' }';
}
function generate(root=path.resolve(__dirname,'../..'),check=false){
  const entries=require('../identity.cjs').registry(root);
  const address=(kind)=>'<noinclude>由 Registry 派生；参数 1 为稳定登记 ID。</noinclude><includeonly>{{#switch:{{{1|}}}'+entries.filter(e=>e.kind===kind||(kind==='pages'&&e.kind==='redirects')).map(e=>'|'+e.id+'='+(kind==='assets'?e.title.split(':').slice(1).join(':'):e.title)).join('')+'|#default=}}</includeonly>';
  const outputs={'wiki/templates/TD2资产.wiki':address('assets'),'wiki/templates/TD2页面地址.wiki':address('pages'),'wiki/modules/TD2编辑数据值.lua':'return {json='+lua(JSON.stringify(data(root)))+'}\n','wiki/modules/TD2效果映射.lua':'return '+lua(Object.fromEntries(references(root).map(r=>[r.id,r.modes])))+'\n',
    'wiki/modules/TD2装备映射.lua':'return '+lua(require('./projection.cjs').reader(require('./database.cjs').load(root),{workspace:root}))+'\n'};
  const registry=JSON.parse(fs.readFileSync(path.join(root,'publishing/registry.json'),'utf8')),generation=require('../generation.cjs');
  generation.apply(generation.plan(root,outputs,registry,'tools/equipment/catalog.cjs@v1'),check);
}
module.exports={data,lua,generate,references};if(require.main===module)generate(undefined,process.argv[2]==='check');
