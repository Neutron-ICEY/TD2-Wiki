/* Isolated server-rendered Reader preview; owns no editor state or save baseline. */
(function(root,factory){
 if(typeof module==="object"&&module.exports)module.exports={create:factory};
 else root.TD2EditorLab.readerPreview={create:factory};
}(typeof globalThis!=="undefined"?globalThis:this,function(environment){
 "use strict";
 const {document,adapter,container}=environment;
 let generation=0,disposed=false,current=null,mode="PvE";
 const status=document.createElement("p"),frame=document.createElement("iframe"),controls=document.createElement("div");
 status.setAttribute("role","status");
 controls.setAttribute("role","group");controls.setAttribute("aria-label","预览模式（不改变编辑数据）");controls.hidden=true;
 frame.title="未保存资料的 Reader 预览";frame.setAttribute("sandbox","");
 frame.style.cssText="width:100%;height:1000px;min-height:85vh;border:1px solid #777";frame.hidden=true;
 const buttons=["PvE","PvP"].map(value=>{
  const button=document.createElement("button");button.type="button";button.textContent="预览 "+value;
  button.addEventListener("click",()=>{if(!disposed&&current){mode=value;render(current);}});
  controls.append(button);return button;
 });
 container.append(status,controls,frame);
 function invalidate(){generation++;buttons.forEach(b=>b.disabled=true);if(!frame.hidden)status.textContent="资料已变化，当前预览已过时，请重新预览。";}
 function escape(value){return String(value).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;");}
 function styleTag(css){return "<style>"+css.replace(/<\/style/gi,"<\\/style")+"</style>";}
 function theme(){
  // Only presentation values observed at the real Reader root; never session/config data.
  const reader=document.querySelector("#mw-content-text"),surface=document.querySelector("#wiki-body");
  if(!reader||!surface)return {css:"",known:false};
  const view=document.defaultView,computed=view.getComputedStyle(reader),background=view.getComputedStyle(surface);
  const declaration=document.createElement("div").style;
  ["--detail-infobox-a","--bg-inner","--td2-pvp-tint","--sub-a","--main-base","--modal","--brand-danger","--brand-default","--detail-navbox-a","--brand-warning","--skin-font-mono","--brand-primary","--font-monospace","--a","--brand-info","--brand-success","--sub-bg","--bg"].forEach(name=>{
   const value=computed.getPropertyValue(name);if(value)declaration.setProperty(name,value);
  });
  const variables=declaration.cssText;declaration.cssText="";
  ["color","font-family","font-size","line-height"].forEach(name=>declaration.setProperty(name,computed.getPropertyValue(name)));
  declaration.setProperty("background-color",background.backgroundColor);
  return {css:":root{"+variables+"}body,#wiki-body{"+declaration.cssText+"}",known:true};
 }
 function render(result){
  const parser=new document.defaultView.DOMParser(),parsed=parser.parseFromString(result.html,"text/html");
  parsed.querySelectorAll("script,iframe,object,embed,base,meta,form,link,input,button,select,textarea").forEach(e=>e.remove());
  parsed.querySelectorAll("*").forEach(e=>Array.from(e.attributes).forEach(a=>{
   const compact=a.value.replace(/[\u0000-\u0020]/g,"");
   if(/^on/i.test(a.name)||/^(?:javascript|vbscript|data:text\/html):/i.test(compact))e.removeAttribute(a.name);
  }));
  // Keep local anchors; external navigation is intentionally unavailable in this read-only view.
  parsed.querySelectorAll("a").forEach(a=>{if(!/^#/.test(a.getAttribute("href")||"")){a.removeAttribute("href");a.setAttribute("title","预览中不打开外部链接");}a.removeAttribute("target");a.removeAttribute("ping");});
  parsed.querySelectorAll('.td2-models.mw-collapsible').forEach(element=>{
   const details=document.createElement('details'),summary=document.createElement('summary');
   details.className='td2-models';summary.textContent=element.getAttribute('data-expandtext');details.append(summary);
   const content=element.querySelector('.mw-collapsible-content');
   if(content){while(content.firstChild)details.append(content.firstChild);element.replaceWith(details);}
  });
  parsed.querySelectorAll(".td2-brand-panel").forEach(panel=>{
   const active=panel.classList.contains("td2-brand-"+mode.toLowerCase());
   panel.hidden=!active;panel.classList.toggle("td2-mode-pvp",active&&mode==="PvP"&&!panel.classList.contains("td2-gear-effect-group")&&!panel.classList.contains("td2-gear-talent-links"));
   if(!active)panel.style.setProperty("display","none","important");
  });
  // Preserve real stylesheet order. No parse modules/config or user HTML scripts execute.
  const styles=[],seen=new Set();
  document.querySelectorAll('link[rel="stylesheet"][href],style').forEach(e=>{
   if(e.hasAttribute("data-td2-editor-style"))return;
   if(e.tagName==="STYLE")styles.push(styleTag(e.textContent));
   else {
    seen.add(e.href);
    let css="";
    try{
     const sheet=Array.from(document.styleSheets).find(sheet=>sheet.href===e.href);
     css=Array.from(sheet?sheet.cssRules:[]).map(rule=>rule.cssText).join("\n");
    }catch(e){}
    // Inlining readable Reader CSS lets a local HTTP preview keep the sandbox's HTTPS/inline style policy.
    styles.push(css.includes(".td2-brand")?styleTag(css):'<link rel="stylesheet" href="'+escape(e.href)+'">');
   }
  });
  parser.parseFromString(result.head,"text/html").querySelectorAll('link[rel="stylesheet"][href]').forEach(e=>{
   const u=new URL(e.getAttribute("href"),document.location.href);
   if(u.origin===document.location.origin&&/\/load\.php$/.test(u.pathname)&&u.searchParams.get("only")==="styles"&&!seen.has(u.href)){seen.add(u.href);styles.push('<link rel="stylesheet" href="'+escape(u.href)+'">');}
  });
  const presentation=theme();
  const hostCSS='body{margin:0}#wiki-outer-body{padding:0}#wiki-body{width:100%;max-width:none;margin:0;padding:12px;box-sizing:border-box}#content{margin:0}#bodyContent{padding:0}.wiki-body-section{width:100%;float:none;padding:0}';
  frame.srcdoc='<!doctype html><html lang="zh-CN" class="'+escape(document.documentElement.className)+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src https: &#39;unsafe-inline&#39;; img-src https: data:; font-src https: data:; script-src &#39;none&#39;; form-action &#39;none&#39;; base-uri &#39;none&#39;">'+styles.join("")+styleTag(presentation.css+hostCSS)+'</head><body class="'+escape(document.body.className)+'"><div id="wiki-outer-body" class="huiji-css-hook"><div id="wiki-body" class="wiki-body"><main id="content"><article class="wiki-body-section"><section id="bodyContent" class="body"><div id="mw-content-text" class="mw-body-content mw-content-ltr">'+parsed.body.innerHTML+'</div></section></article></main></div></div></body></html>';
  frame.hidden=false;controls.hidden=false;
  buttons.forEach((b,i)=>{b.disabled=false;b.setAttribute("aria-pressed",String(mode===(i?"PvP":"PvE")));});
  status.textContent="未保存资料预览 · "+mode+"；仅切换服务器已渲染的内容，未写入页面。外部链接及其他脚本交互不执行。"+(!presentation.known?" 无法取得Reader主题，样式仅供参考。":"")+(result.warnings.length?" 站点解析提示："+result.warnings.join("；"):"");
 }
 return {
  invalidate,
  async show(text){
   const request=++generation;buttons.forEach(b=>b.disabled=true);status.textContent="正在解析未保存资料…";
   try{
    const result=await adapter.preview(text);
    if(disposed||request!==generation)return null;
    current=result;render(result);
    return {modules:result.modules,styles:result.styles,warnings:result.warnings};
   }catch(e){if(!disposed&&request===generation)status.textContent="预览失败，输入仍保留："+(e.code||e.message);throw e;}
  },
  dispose(){disposed=true;generation++;current=null;frame.remove();controls.remove();status.remove();}
 };
}));
