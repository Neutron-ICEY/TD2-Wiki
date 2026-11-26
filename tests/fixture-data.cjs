'use strict';
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const fixtures=path.join(__dirname,'fixtures'),index=JSON.parse(fs.readFileSync(path.join(fixtures,'regression-inputs.json'),'utf8'));
function read(name){
 const entry=index[name];assert(entry,'Unknown regression input');
 assert.equal(path.basename(entry.file),entry.file,'Invalid regression filename');
 const data=zlib.gunzipSync(fs.readFileSync(path.join(fixtures,entry.file)));
 assert.equal(crypto.createHash('sha256').update(data).digest('hex'),entry.sha256,'Regression input SHA256 mismatch');
 return JSON.parse(data.toString('utf8'));
}
module.exports={read};
