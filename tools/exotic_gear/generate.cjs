'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const data=require('./data.cjs'),root=path.resolve(__dirname,'../..');
function sources(){return {
  'wiki/modules/TD2装备属性数据.lua':data.readerData(),
  'wiki/templates/奇特装备信息.wiki':'<noinclude>奇特装备 Reader，按资料身份读取共享映射。</noinclude><includeonly>{{#invoke:TD2奇特装备|render}}</includeonly>\n',
  'wiki/templates/奇特装备属性槽.wiki':'<noinclude>奇特装备有序属性槽记录，由所属页面消费。</noinclude><includeonly>{{#invoke:TD2奇特装备|slot}}</includeonly>\n'
};}
if(require.main===module){
  assert(['generate','check'].includes(process.argv[2]),'Use generate or check');
  const registry=JSON.parse(fs.readFileSync(path.join(root,'publishing/registry.json'),'utf8'));
  const generated=require('../generation.cjs');
  generated.apply(generated.plan(root,sources(),registry,'tools/exotic_gear/generate.cjs@v1'),process.argv[2]==='check');
  console.log('Exotic resources '+process.argv[2]+' passed');
}
module.exports={sources};
