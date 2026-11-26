'use strict';
const path=require('node:path'),identity=require('../identity.cjs'),crafting=require('./crafting.cjs');
const root=path.resolve(__dirname,'../..');
function rows(entity,workspace=root,blueprints){
  blueprints??=crafting.playerBlueprints(crafting.load(workspace),require('./acquisition.cjs').rules(workspace).unavailable_blueprints);
  const models=entity.collections?.武器型号资料?.rows||[];
  const modelsData=models.map(record=>record.data);
  const exclusiveDyes=new Set(modelsData.flatMap(model=>(model.skins||[])
    .filter(skin=>skin.preattached&&skin.tags.some(tag=>tag.startsWith('Skin_Named_Exclusive_')))
    .map(skin=>skin.uid)));
  // A sibling may inherit the socket for a named gun's default dye.
  const modelSkins=model=>(model?.skins||[]).filter(skin=>skin.preattached||!exclusiveDyes.has(skin.uid));
  const base=modelsData.find(model=>model.kind==='normal');
  const baseSkins=new Set(modelSkins(base).map(skin=>skin.uid));
  return models.map(record=>{
    const r=structuredClone(record.data),uids=[r.装备UID,...(r.variants||[]).map(v=>v.uid)];
    if(r.asset_ref)r.image=identity.asset(r.asset_ref,workspace).title.split(':').slice(1).join(':');
    r.skins=modelSkins(r).filter(skin=>r.kind!=='named'||skin.preattached||!baseSkins.has(skin.uid)).map(skin=>{
      const card={name:skin.name};
      if(skin.asset_ref)card.image=identity.asset(skin.asset_ref,workspace).title.split(':').slice(1).join(':');
      return card;
    });
    r.blueprints=Object.entries(blueprints).filter(([,b])=>b.targets.some(uid=>uids.includes(uid))).map(([uid,b])=>({uid,name:b.name||r.装备名称,purpose:b.purpose}));
    delete r.asset_ref;delete r.variants;
    return r;
  });
}
module.exports={rows};
