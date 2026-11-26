(function(root,factory){
  if(typeof module==="object" && module.exports) module.exports=factory();
  else (root.TD2EditorLab=root.TD2EditorLab||{}).contract=factory();
}(typeof globalThis!=="undefined"?globalThis:this,function(){
  "use strict";
  const slots={mask:"面具",backpack:"背包",chest:"胸甲",gloves:"手套",holster:"枪套",kneepads:"护膝"};
  return {slots};
}));
