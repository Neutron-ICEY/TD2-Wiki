// Local fixtures supply server context only; reader.js is the unmodified production source.
(function () {
  const page=JSON.parse(document.getElementById('preview-page').textContent);
  const params=new URLSearchParams(location.search), role=params.get('role')||'admin';
  const admin=role==='admin'||role==='blocked', id=admin?1:role==='user'?2:0;
  const groups=admin?['sysop','verified']:id?['user','verified']:['*'];
  const values={wgNamespaceNumber:0,wgAction:'view',wgIsArticle:true,wgArticleId:params.has('noid')?0:page.pageid,
    wgPageName:page.title,wgUserId:id,wgUserName:admin?'Preview admin':null,wgUserGroups:groups};
  document.getElementById('preview-role').value=role;
  document.getElementById('preview-role').addEventListener('change',function(){params.set('role',this.value);location.search=params;});
  document.querySelectorAll('[data-preview-page]').forEach(a=>a.search=params);
  const nativeClipboard=navigator.clipboard;
  const readClipboard=document.createElement('button');readClipboard.type='button';readClipboard.textContent='读取刚复制的链接';
  document.getElementById('clipboard-proof').parentElement.before(readClipboard);
  readClipboard.addEventListener('click',async()=>{
    try { document.getElementById('clipboard-proof').value=await nativeClipboard.readText(); }
    catch(error) { document.getElementById('clipboard-proof').value=error.name; }
  });
  window.mw={config:{get:key=>values[key]},util:{getUrl:(title,query)=>'https://td2.huijiwiki.com/wiki/'+encodeURIComponent(title)+(query?'?'+new URLSearchParams(query):'')},
    huijiApi:{getPageUrlById:(pid,prefix)=>'https://'+prefix+'.huijiwiki.com/p/'+pid},loader:{using:()=>Promise.resolve()},
    Api:function(){this.get=()=>Promise.resolve({query:{userinfo:{id,groups,rights:['edit']},pages:[{pageid:page.pageid,title:page.title,ns:0,actions:{edit:role!=='blocked'}}]}});}};
  if(params.has('noclipboard')) Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});
  // site-entry.js 的页面合同与准入由 test_page_actions.cjs 执行真实源码验证。
  if(admin&&page.form){
    const link=document.createElement('a');link.id='td2-js-edit-entry';link.textContent='编辑表单';link.href='#preview-form';
    link.addEventListener('click',e=>{e.preventDefault();document.getElementById('preview-form').hidden=false;});
    document.getElementById('firstHeading').appendChild(link);
  }
}());
