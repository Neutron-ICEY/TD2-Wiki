'use strict';
const fs=require('node:fs'),path=require('node:path');
function workspace(root=process.env.TD2_WIKI_ROOT||path.resolve(__dirname,'../../..')){
  const resolved=path.resolve(root);
  if(!fs.existsSync(path.join(resolved,'data/equipment/records.json'))||!fs.existsSync(path.join(resolved,'data/equipment/attributes.json')))throw new Error('EDITOR_ROOT_INPUTS_NOT_FOUND: '+resolved);
  return resolved;
}
let cached;
function equipment(root){
  root=workspace(root);
  const recordFile=fs.statSync(path.join(root,'data/equipment/records.json'));
  const registryFile=fs.statSync(path.join(root,'publishing/registry.json'));
  const stamp=root+':'+recordFile.mtimeMs+':'+recordFile.size+':'+registryFile.mtimeMs+':'+registryFile.size;
  if(cached?.stamp===stamp)return cached.data;
  const data={catalog:require(path.join(root,'tools/equipment/projection.cjs')).editor(require(path.join(root,'tools/equipment/database.cjs')).load(root))};
  cached={stamp,data};return data;
}
module.exports={workspace,equipment};
