const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {filterBrand,isLevelBoost}=require('../tools/brand_sets/member-filter.cjs');
const input=require('./fixture-data.cjs').read('brand-inputs');
test('reviewed named drop variants collapse without changing canonical recipes or ordinary models',()=>{
 const before=JSON.stringify(input);
 const changed=input.brands.map(b=>[b,filterBrand(b)]).filter(([,b])=>b.excluded_named_variants?.length);
 assert.deepEqual(changed.map(([b])=>b.title),['戈兰装备有限公司','毒蜥守卫队']);
 for(const [original,result] of changed){
  assert.equal(result.named_records.length,original.named_records.length-1);
  const salvaged=new Set((result.excluded_salvaged_members||[]).map(x=>x.uid));
  assert.deepEqual(result.ordinary_models,original.ordinary_models.filter(x=>!isLevelBoost(x)&&!salvaged.has(x.uid)));
  const canonical=result.named_records.find(x=>x.uid===result.excluded_named_variants[0].canonical_uid);
  assert.equal(canonical,original.named_records.find(x=>x.uid===canonical.uid));assert(canonical.blueprint);
  assert.deepEqual(filterBrand(result),result);
 }
 assert.equal(JSON.stringify(input),before);
});
test('missing canonical record fails instead of silently discarding equipment',()=>{
 const b=input.brands.find(b=>b.title==='戈兰装备有限公司');
 const only=b.named_records.filter(x=>x.internal_name.endsWith('_alpha'));
 assert.throws(()=>filterBrand({...b,members:only,named_records:only,ordinary_models:[]}),/IDENTITY_MISMATCH/);
});
