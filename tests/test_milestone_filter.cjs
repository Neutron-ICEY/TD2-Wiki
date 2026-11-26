const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {isMilestone,filterBrand}=require('../tools/brand_sets/member-filter.cjs');
test('native marker filters ordinary and named records while preserving same-name normal equipment',()=>{
 const normal={uid:'normal',internal_name:'player_gear_chest_w_01',name:{zh:'Same name'},blueprint:{uid:'recipe'}};
 const reward={uid:'reward',internal_name:'player_gear_chest_w_01_milestone_lvl25',name:{zh:'Same name'}};
 const named={uid:'named',internal_name:'player_gear_named_milestone_lvl10'};
 const input={members:[normal,reward,named],ordinary_models:[normal,reward],named_records:[named],material_name:'Material'};
 const before=JSON.stringify(input),result=filterBrand(input);
 assert.equal(JSON.stringify(input),before);assert.deepEqual(result.members,[normal]);assert.deepEqual(result.ordinary_models,[normal]);assert.deepEqual(result.named_records,[]);
 assert.equal(result.ordinary_models[0].blueprint,normal.blueprint);assert.equal(result.material_name,input.material_name);
 assert.equal(result.excluded_milestone_members.length,2);assert.deepEqual(filterBrand(result),result);
 assert(!isMilestone({internal_name:'player_gear_normal',name:{zh:'milestone'}}));assert(!isMilestone({internal_name:'player_gear_milestones_01'}));
});
test('verified native samples remove nine milestone rewards without changing normal and named records',()=>{
 const input=JSON.parse(fs.readFileSync(path.resolve(__dirname,'fixtures/milestone-native-members.json'),'utf8'));
 assert.deepEqual(input.brands.map(b=>[b.title,b.members.filter(isMilestone).length]),[['芬里斯集团公司',6],['先驱工业',3]]);
 const changed=input.brands.map(brand=>({before:brand,after:filterBrand(brand)})).filter(x=>x.before.members.some(isMilestone));
 assert.equal(changed.length,2);
 for(const {before,after} of changed){
  assert.equal(after.members.length,before.title==='先驱工业'?8:12);
  assert.equal(after.ordinary_models.length,before.title==='先驱工业'?6:11);
  assert.equal(after.excluded_milestone_members.length,before.title==='先驱工业'?3:6);
  assert.equal(after.excluded_level_boost_members?.length||0,before.title==='先驱工业'?0:4);
  assert.equal(after.excluded_salvaged_members?.length||0,before.title==='先驱工业'?0:2);
  assert.deepEqual(after.named_records,before.named_records);
  for(const item of after.members)assert.equal(item,before.members.find(x=>x.uid===item.uid));
 }
});
