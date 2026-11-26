(function (root, factory) {
  if (root && root.mw) root.mw.td2EditorEntryPolicy = factory(typeof globalThis!=='undefined'&&globalThis.TD2EditorLab?globalThis.TD2EditorLab.pageScope:null);
  else if (typeof module === 'object' && module.exports) module.exports = factory(require('./page-scope.js'));
}(this, function (scope) {
  'use strict';
  const forms = [{id:'brand', enabled:true, contractPages:true,
    runtime:{title:'Gadget:TD2EditorRuntime.js',exportName:'td2EditorRuntime',expected:'REEDIT_BUILD_VERSION',revision:'REEDIT_RUNTIME_REVISION'}}];
  function isAdmin(user) {
    return !!user && user.id > 0 && !!user.name && !user.anon && Array.isArray(user.groups) && user.groups.includes('sysop');
  }
  function select(context, available=forms) {
    if(context.origin!=='https://td2.huijiwiki.com'||context.namespace!==0||context.action!=='view'||context.historical||!(context.pageid>0)||!isAdmin(context.user))return null;
    const enabled=available.filter(f=>f.enabled&&f.contractPages);
    return enabled.length===1?{form:enabled[0],target:{title:context.title,pageid:context.pageid,modes:['edit']},mode:'edit',contractPage:true}:null;
  }
  function verify(context,match,response) {
    const query=response&&response.query,user=query&&query.userinfo,pages=query&&query.pages,page=pages&&pages.length===1&&pages[0];
    return isAdmin(user)&&user.id===context.user.id&&user.name===context.user.name&&Array.isArray(user.rights)&&user.rights.includes('edit')&&!!page&&page.title===match.target.title&&page.ns===0&&!page.missing&&page.pageid===match.target.pageid&&!!page.actions&&page.actions.edit===true;
  }
  return {forms,isAdmin,select,verify,scope};
}));
