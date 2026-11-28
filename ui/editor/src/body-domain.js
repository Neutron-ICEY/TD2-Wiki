/* Bounded page-body editing. Scanner owns main-template offsets; no page regex parser. */
(function(root,factory){
 if(typeof module==="object"&&module.exports)module.exports=factory();
 else root.TD2EditorLab.body=factory();
}(typeof globalThis!=="undefined"?globalThis:this,function(){
 "use strict";
 function range(doc){
  const start=doc.main.end, suffix=doc.suffix;
  if(doc.prefix.trim()!=="")return {editable:false,reason:"主模板前含额外内容，正文归属未确认；保持原文。",start,end:start,value:""};
  // Only the prose before the first separate template/tag/comment/category is editable.
  // Everything after that boundary is an opaque protected remainder, never tidied.
  let end=suffix.length;
  for(let i=0;i<suffix.length;i++){
   if(suffix.startsWith("{{",i)||suffix[i]==="<"){end=i;break;}
   if(suffix.startsWith("[[",i)){
    const close=suffix.indexOf("]]",i+2);
    if(close<0)return {editable:false,reason:"正文链接未闭合。",start,end:start,value:""};
    if(/^\s*(?:category|分类|分類)\s*:/i.test(suffix.slice(i+2,close))){end=i;break;}
    i=close+1;
   }
  }
  // Preserve the existing separator and whitespace adjacent to protected content.
  let from=0;while(from<end&&/\s/.test(suffix[from]))from++;
  let to=end;while(to>from&&/\s/.test(suffix[to-1]))to--;
  return {editable:true,start:start+from,end:start+to,protectedStart:start+end,value:suffix.slice(from,to),
   reason:end<suffix.length?"后续分类、注释、模板等区域保持原样，不在此输入框内。":""};
 }
 function replacement(doc,span,value){
  const {start,end,protectedStart}=span,raw=doc.raw;
  const hasProtected=protectedStart<raw.length;
  // Clearing the last body removes its orphaned separators before exact save readback.
  if(!value&&!hasProtected)return {start:doc.main.end,end:protectedStart,text:""};
  const after=raw.slice(end,protectedStart);
  if(!value){
   const separated=raw.slice(doc.main.end,start).includes("\n")||after.includes("\n");
   return {start,end,text:separated?"":"\n"};
  }
  // Headings and lists need to start on a new line, including next to a protected block.
  const before=raw[start-1]==="\n"?"":"\n";
  const separator=hasProtected&&!after.includes("\n")?"\n":"";
  return {start,end,text:before+value+separator};
 }
 function validate(value){
  if(typeof value!=="string"||value.length>131072)return "正文长度超出当前支持范围。";
  if(/[\x00-\x08\x0b-\x1f\x7f<>]|{{|}}|\x7e{3}|__|(?:^|\n)\s*\{\|/i.test(value))return "正文支持文字、标题、列表和普通链接；暂不接受模板、HTML、签名替换或行为指令。";
  if(value.trim()!==value)return "正文首尾请勿增加空白；已有分隔换行由系统保留。";
  for(let i=0;i<value.length;i++){
   if(value.startsWith("[[",i)){
    const end=value.indexOf("]]",i+2),part=value.slice(i+2,end);
    if(end<0||/[\[\]{}]/.test(part)||/^\s*(?:category|分类|分類)\s*:/i.test(part))return "请使用完整普通链接；分类区域保持只读。";
    i=end+1;
   }else if(value[i]==="["||value[i]==="]")return "当前正文仅支持双括号普通链接。";
  }
  return "";
 }
 return {range,replacement,validate};
}));
