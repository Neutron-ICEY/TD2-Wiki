'use strict';
module.exports=function(){
  const id='gear_set:synthetic_test',ids=['two_a','two_b','three','core','chest','backpack'];
  const effects=ids.map((key,i)=>({id:'gear_effect:'+key,role:i<3?'bonus':i===3?'core_talent':'slot_talent',activation_count:[2,2,3,4,4,4][i],slot:i===4?'chest':i===5?'backpack':null,depends_on:i>3?['gear_effect:core']:[],evidence:['NON-GAME-FACT test fixture'],review:'approved',modes:{PvE:{content:i<3?{attribute:'TEST '+key,value:String(i),unit:'%'}:{name:'TEST '+key,description:'合成描述\n第二段',condition:'合成触发条件'},review:'approved',evidence:['NON-GAME-FACT test fixture']},PvP:null}}));
  return {schema_version:1,sets:[{id,native_uid:null,effect_ids:effects.map(e=>e.id),evidence:['NON-GAME-FACT test fixture']}],effects};
};
