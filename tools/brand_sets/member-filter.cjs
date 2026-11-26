const isMilestone=item=>/(^|_)milestone(_|$)/i.test(item.internal_name||'');
const isLevelBoost=item=>/(^|_)level\d+boost(_|$)/i.test(item.internal_name||'');
const salvagedPolicy=require('./excluded-salvaged-models.json');
const salvagedModels=new Map(salvagedPolicy.models.map(item=>[item.uid,item]));
const craftedVariants={
  '4CDCE5B25BB61F4E0002CD20F5D583E3':'4CDCE5B25AA10CBA0006262B5ABACEF6',
  '4CDCE5B25B97DC790002A1AFCBA5ED10':'4CDCE5B25AA117F8000066ED50B5528B'
};
const namedVariants={
  '075801E25E217998000257C8D94C2117':'BFAAA1FC5E2078BB0006D2960C76ACA4',
  '075801E25E217AAA00034FCCF1298784':'BFAAA1FC5E1F2237000513C9B67D554A'
};
function filterBrand(brand){
  const keys=['members','ordinary_models','named_records'];
  const salvaged=new Map();
  for(const key of keys)for(const item of brand[key]||[]){
    const reviewed=salvagedModels.get(item.uid);
    if(!reviewed)continue;
    if(key==='named_records'||item.is_named===true)
      throw new Error('SALVAGED_ORDINARY_MODEL_CLASSIFICATION_CONFLICT: '+item.uid);
    if(item.internal_name!==reviewed.internal_name||(brand.title&&brand.title!==reviewed.brand))
      throw new Error('SALVAGED_MODEL_IDENTITY_MISMATCH: '+item.uid);
    salvaged.set(item.uid,{...reviewed,reason:salvagedPolicy.reason});
  }
  if(salvaged.size)brand={...brand,
    members:(brand.members||[]).filter(item=>!salvaged.has(item.uid)),
    ordinary_models:(brand.ordinary_models||[]).filter(item=>!salvaged.has(item.uid)),
    excluded_salvaged_members:[...(brand.excluded_salvaged_members||[]),...salvaged.values()]};
  const merged=[],replacements=new Map();
  for(const item of brand.ordinary_models||[]){
    const canonicalUid=craftedVariants[item.uid];
    if(!canonicalUid)continue;
    const canonical=brand.ordinary_models.find(other=>other.uid===canonicalUid);
    if(!canonical||canonical.gear_slot!==item.gear_slot||canonical.name?.zh!==item.name?.zh||
      !item.blueprint||item.blueprint.crafted_item_uid!==item.uid||
      (canonical.blueprint&&JSON.stringify(canonical.blueprint)!==JSON.stringify(item.blueprint)))
      throw new Error('CRAFTED_VARIANT_IDENTITY_OR_BLUEPRINT_CONFLICT: '+item.uid);
    replacements.set(canonicalUid,{...canonical,blueprint:item.blueprint});
    merged.push({uid:item.uid,canonical_uid:canonicalUid,internal_name:item.internal_name,reason:'CRAFTED_MODEL_VARIANT',blueprint_uid:item.blueprint.uid});
  }
  if(merged.length)brand={...brand,...Object.fromEntries(keys.map(key=>[key,(brand[key]||[]).filter(item=>!craftedVariants[item.uid]).map(item=>replacements.get(item.uid)||item)])),
    merged_crafted_variants:[...(brand.merged_crafted_variants||[]),...merged]};
  const boosts=new Map(keys.flatMap(key=>brand[key]||[]).filter(isLevelBoost).map(item=>[item.uid,item]));
  if(boosts.has(undefined)||boosts.has(''))throw new Error('LEVEL_BOOST_UID_REQUIRED');
  if(boosts.size)brand={...brand,...Object.fromEntries(keys.map(key=>[key,(brand[key]||[]).filter(item=>!boosts.has(item.uid))])),
    excluded_level_boost_members:[...(brand.excluded_level_boost_members||[]),...Array.from(boosts.values(),item=>({uid:item.uid,internal_name:item.internal_name,reason:'LEVEL_BOOST_PRESET'}))]};
  const items=keys.flatMap(key=>brand[key]||[]),variants=new Map();
  for(const item of items){
    const canonicalUid=namedVariants[item.uid];
    if(!canonicalUid)continue;
    const canonical=items.find(other=>other.uid===canonicalUid);
    if(!canonical||!item.name?.guid||item.name.guid!==canonical.name?.guid||item.gear_slot!==canonical.gear_slot||
      !item.generation_binding?.shared_config_link_uid||item.generation_binding.shared_config_link_uid!==canonical.generation_binding?.shared_config_link_uid)
      throw new Error('NAMED_VARIANT_IDENTITY_MISMATCH: '+item.uid);
    variants.set(item.uid,{uid:item.uid,internal_name:item.internal_name,canonical_uid:canonicalUid,reason:'NAMED_DROP_VARIANT'});
  }
  if(variants.size)brand={...brand,...Object.fromEntries(keys.map(key=>[key,(brand[key]||[]).filter(item=>!variants.has(item.uid))])),
    excluded_named_variants:[...(brand.excluded_named_variants||[]),...variants.values()]};
  const excluded=new Map(keys.flatMap(key=>brand[key]||[]).filter(isMilestone).map(item=>[item.uid,item]));
  if(!excluded.size)return brand;
  if(excluded.has(undefined)||excluded.has(''))throw new Error('MILESTONE_UID_REQUIRED');
  return {...brand,...Object.fromEntries(keys.map(key=>[key,(brand[key]||[]).filter(item=>!excluded.has(item.uid))])),
    excluded_milestone_members:[...(brand.excluded_milestone_members||[]),...Array.from(excluded.values(),item=>({uid:item.uid,internal_name:item.internal_name,reason:'MILESTONE_BUILD'}))]};
}
module.exports={isMilestone,isLevelBoost,filterBrand};
