const fs=require('fs'),path=require('path'),assert=require('assert/strict'),crypto=require('crypto');
const base=path.resolve(__dirname,'..');
const rootFlag=process.argv.indexOf('--root');
assert(rootFlag<0||process.argv[rootFlag+1],'--root requires a workspace');
const root=path.resolve(rootFlag<0?path.resolve(base,'../..'):process.argv[rootFlag+1]);
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const bindings={runtime:{file:'TD2EditorRuntime.js',title:'Gadget:TD2EditorRuntime.js'},entry:{file:'TD2EditorEntry.js',title:'Gadget:TD2EditorEntry.js'}};
const names=["parser","body-domain","text-boundary","contract","state","source-patches","page-fields","mapped-domain","local-session","ui-primitives","mapped-ui","editor-view","reader-preview","page-scope","mediawiki-adapter","site-session","site-expanded-bootstrap"];
const version=(inputs,toolchain)=>'editor-'+hash(JSON.stringify(inputs)+JSON.stringify(toolchain)).slice(0,16);
if(process.argv[2]==='--bind-entry'){
  const candidate=path.resolve(process.argv[3]),receipt=JSON.parse(fs.readFileSync(process.argv[4],'utf8')),out=path.resolve(process.argv[5]);
  assert(!fs.existsSync(out),'Use a fresh bound-entry directory');
  const manifest=JSON.parse(fs.readFileSync(path.join(candidate,'manifest.json'),'utf8'));
  assert.deepEqual(manifest.resourceBindings,bindings);
  assert(Number.isSafeInteger(receipt.pageid)&&receipt.pageid>0);
  assert(Number.isSafeInteger(receipt.revid)&&receipt.revid>0);
  assert(['零件:TD2EditorRuntime.js',bindings.runtime.title].includes(receipt.title));
  const runtime=fs.readFileSync(path.join(candidate,bindings.runtime.file),'utf8'),entry=fs.readFileSync(path.join(candidate,bindings.entry.file),'utf8');
  assert.equal(receipt.raw,runtime,'Runtime readback must match exact candidate bytes');
  for(const [role,content] of [['runtime',runtime],['entry',entry]])assert.equal(hash(content),manifest.files.find(f=>f.name===bindings[role].file).sha256);
  assert(entry.includes('REEDIT_RUNTIME_REVISION'));
  assert.equal(entry.split(bindings.runtime.title).length,2);
  // Entry uses the revision from the exact Runtime readback verified above.
  const bound=entry.replace(/REEDIT_RUNTIME_REVISION/g,String(receipt.revid));
  fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,bindings.entry.file),bound);
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({version:manifest.version,production_approved:false,
    runtime:{pageid:receipt.pageid,title:receipt.title,revision:receipt.revid,sha256:hash(runtime)},
    entry:{title:bindings.entry.title,sha256:hash(bound)}},null,2)+'\n');
  console.log('Bound formal Entry to verified Runtime revision '+receipt.revid);
}else{
  const verifying=process.argv[2]==='--verify-inputs';
  assert(verifying?process.argv[3]:process.argv[2]&&!process.argv[2].startsWith('--'),'Provide a fresh candidate directory or --verify-inputs editor-directory');
  const out=verifying?null:path.resolve(process.argv[2]),editor=verifying?path.resolve(process.argv[3]):path.join(out,'editor');
  if(!verifying)assert(!fs.existsSync(out),'Use a fresh candidate directory');
  if(verifying){
    const saved=JSON.parse(fs.readFileSync(path.join(editor,'manifest.json'),'utf8'));
    const expected=new Set(['ui/editor/editor.css',...names.map(n=>'ui/editor/src/'+n+'.js'),'ui/editor/src/site-entry-policy.js','ui/editor/src/site-entry.js','ui/editor/tooling/package.json','ui/editor/production/build.cjs','ui/editor/tooling/package-lock.json']);
    assert.equal(saved.inputs.length,expected.size,'Editor input set differs');
    assert.deepEqual(new Set(saved.inputs.map(i=>i.source)),expected,'Editor input set differs');
    assert.equal(saved.version,version(saved.inputs,saved.toolchain),'Editor input identity/version differs');
    assert.deepEqual(saved.files.map(f=>f.name).sort(),Object.values(bindings).map(b=>b.file).sort());
    for(const input of saved.inputs)assert.equal(hash(fs.readFileSync(path.resolve(root,input.source))),input.sha256,'Editor input changed: '+input.source);
    for(const file of saved.files)assert.equal(hash(fs.readFileSync(path.join(editor,file.name))),file.sha256,'Editor artifact changed: '+file.name);
    console.log(saved.version+' inputs and artifacts verified');process.exit(0);
  }
  const inputs=[];
  function read(file){const bytes=fs.readFileSync(file),input={source:path.relative(root,file).replace(/\\/g,'/'),sha256:hash(bytes)},prior=inputs.find(row=>row.source===input.source);assert(!prior||prior.sha256===input.sha256,'Input changed during build: '+input.source);inputs.push(input);return bytes.toString('utf8');}
  const config={cutover:true,css:read(path.join(base,'editor.css'))};
  const setup='globalThis.TD2EditorLab=globalThis.TD2EditorLab||{};\n';
  const sources=Object.fromEntries(names.map(n=>[n,read(path.join(base,'src',n+'.js'))]));
  const bootstrapNames=['parser','page-scope','mediawiki-adapter'];
  const bootstrap=bootstrapNames.map(n=>sources[n]).join('\n');
  const modules=setup+names.map(n=>sources[n]).join('\n');
  const runtimeModules=setup+names.filter(n=>!bootstrapNames.includes(n)).map(n=>sources[n]).join('\n');
  const entrySources=['parser','page-scope','site-entry-policy','site-entry'].map(n=>read(path.join(base,'src',n+'.js'))).join('\n');
  read(path.join(base,'tooling/package.json'));read(__filename);
  const lock=read(path.join(base,'tooling/package-lock.json')),locked=JSON.parse(lock).packages;
  for(const [name,definition] of Object.entries(locked))if(name&&definition.version)assert.equal(JSON.parse(fs.readFileSync(path.join(base,'tooling',name,'package.json'),'utf8')).version,definition.version,'Installed toolchain differs from lock: '+name);
  const toolchain={node:process.versions.node,babel:require('../tooling/node_modules/@babel/core/package.json').version};
  const inputIdentity=[...new Map(inputs.map(i=>[i.source,i])).values()];
  config.version=version(inputIdentity,toolchain);
  const guard='if(location.origin!=="https://td2.huijiwiki.com"||mw.config.get("wgNamespaceNumber")!==0||mw.config.get("wgAction")!=="view"||!mw.config.get("wgUserId")||!(mw.config.get("wgUserGroups")||[]).includes("sysop"))return;';
  // Runtime and Entry use a local globalThis to keep TD2EditorLab out of the page's globals.
  const runtime='(function(module,exports,require){'+guard+'mw.td2EditorRuntime={version:'+JSON.stringify(config.version)+',open:async function(opts){var adapter;var globalThis={};\n'+bootstrap+'\nadapter=globalThis.TD2EditorLab.mediawikiAdapter.create(new mw.Api(),{origin:location.origin,target:mw.config.get("wgPageName").replace(/_/g," "),pageid:mw.config.get("wgArticleId"),enableWrites:true,contractPages:true});\n'+runtimeModules+'\nvar config='+JSON.stringify(config)+';config.target=mw.config.get("wgPageName").replace(/_/g," ");config.pageid=mw.config.get("wgArticleId");config.standardURL=mw.util.getUrl(config.target,{action:"edit"});return globalThis.TD2EditorLab.siteHost.mount({document:document,window:window,lab:globalThis.TD2EditorLab,config:config,adapter:adapter,onExit:opts.onExit});}};}());';
  const babel=require('../tooling/node_modules/@babel/core'),preset=require.resolve('../tooling/node_modules/@babel/preset-env');
  // The IE 11 target lowers syntax for Huiji ResourceLoader's ES5 minifier. Runtime still uses modern browser APIs.
  const compile=source=>'(function(){\n'+babel.transformSync(source,{presets:[[preset,{targets:{ie:'11'},modules:false}]],sourceType:'script',babelrc:false,configFile:false}).code+'\n}());';
  const entry=compile('(function(module,exports,require){var globalThis={};\n'+entrySources.replace(/REEDIT_BUILD_VERSION/g,config.version).replace(/ENTRY_BUILD_ID/g,config.version+'-entry')+'\n}());');
  const files={[bindings.runtime.file]:compile(runtime),[bindings.entry.file]:entry};
  const manifest={version:config.version,releaseMode:'formal',production_approved:false,resourceBindings:bindings,toolchain,inputs:inputIdentity,files:Object.entries(files).map(([name,content])=>({name,sha256:hash(content)}))};
  for(const input of inputIdentity)assert.equal(hash(fs.readFileSync(path.resolve(root,input.source))),input.sha256,'Input changed during build: '+input.source);
    fs.mkdirSync(editor,{recursive:true});
    if(process.argv.includes('--local-preview')){
      const preview=path.join(out,'local-preview');fs.mkdirSync(preview);
      const catalog=require(path.join(root,'tools/equipment/catalog.cjs')).data(root);
      fs.writeFileSync(path.join(preview,'modules.js'),'var catalog='+JSON.stringify(catalog)+';\n'+modules);
      fs.writeFileSync(path.join(preview,'config.json'),JSON.stringify({...catalog,...config}));
    }
    for(const [name,content] of Object.entries(files))fs.writeFileSync(path.join(editor,name),content);
    fs.writeFileSync(path.join(editor,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
    console.log(config.version+' built from maintained sources in '+editor);

}
