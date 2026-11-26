const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {filterBrand,isLevelBoost}=require('../tools/brand_sets/member-filter.cjs');
const input=require('./fixture-data.cjs').read('brand-inputs');
test('twenty boost presets excluded, two crafted models merged with original recipe targets intact',()=>{
 const before=JSON.stringify(input);let boosts=0,crafted=0;
 for(const b of input.brands){
  const a=filterBrand(b);boosts+=(a.excluded_level_boost_members||[]).length;
  assert(!a.members.some(isLevelBoost));assert.deepEqual(filterBrand(a),a);
  for(const v of a.merged_crafted_variants||[]){
   crafted++;const old=b.ordinary_models.find(x=>x.uid===v.uid),kept=a.ordinary_models.find(x=>x.uid===v.canonical_uid);
   assert.equal(kept.blueprint,old.blueprint);assert.equal(kept.blueprint.crafted_item_uid,old.uid);
   assert(!a.members.some(x=>x.uid===old.uid));
   assert.equal(a.members.find(x=>x.uid===kept.uid),kept);
  }
  assert.deepEqual(a.material_name,b.material_name);
  assert.equal(a.members.length,a.ordinary_models.length+a.named_records.length);
 }
 assert.equal(boosts,20);assert.equal(crafted,2);assert.equal(JSON.stringify(input),before);
});
test('unreviewed crafted records and ordinary same-name equipment survive',()=>{
 const ordinary={uid:'a',internal_name:'normal',name:{zh:'same'}};
 const crafted={uid:'b',internal_name:'other_crafted_01',name:{zh:'same'}};
 const b={members:[ordinary,crafted],ordinary_models:[ordinary,crafted],named_records:[]};
 assert.deepEqual(filterBrand(b),b);
 assert(!isLevelBoost({internal_name:'level30booster'}));
});
test('missing canonical or recipe association blocks a reviewed crafted merge',()=>{
 const b=input.brands.find(x=>x.title==='彼得罗夫防御集团');
 const bad=structuredClone(b);bad.ordinary_models.find(x=>x.internal_name==='player_gear_holster_d_crafted_01').blueprint=null;
 assert.throws(()=>filterBrand(bad),/CRAFTED_VARIANT/);
});
