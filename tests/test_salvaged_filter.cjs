const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {filterBrand}=require('../tools/brand_sets/member-filter.cjs');
const policy=require('../tools/brand_sets/excluded-salvaged-models.json');
const reviewed=new Set(policy.models.map(item=>item.uid));
const native=require('./fixture-data.cjs').read('salvaged-native');
function nativeText(relative){const row=native[relative];assert(row,'Missing native fixture: '+relative);assert.equal(require('node:crypto').createHash('sha256').update(row.text).digest('hex'),row.sha256);return row.text;}
const universe=require('./fixture-data.cjs').read('brand-universe');
const input=require('./fixture-data.cjs').read('brand-inputs');

test('all 29 approved native identities in 15 brands are excluded while their parent UIDs survive',()=>{
 assert.equal(policy.models.length,29);assert.equal(reviewed.size,29);
 assert.equal(new Set(policy.models.map(item=>item.brand)).size,15);
 let removed=0,changed=0;
 for(const brand of universe.brands){
  const selected=policy.models.filter(item=>item.brand===brand.title);
  if(!selected.length)continue;
  const selectedIds=new Set(selected.flatMap(item=>[item.uid,item.parent_uid]));
  const members=brand.members.filter(item=>selectedIds.has(item.uid));
  for(const item of selected){
   assert(members.some(member=>member.uid===item.uid));
   const parent=members.find(member=>member.uid===item.parent_uid);assert(parent);
   const raw=nativeText(item.resource_path);
   assert(raw.includes('ArmorItem '+item.internal_name+' < uid='+item.uid+' > : '+parent.internal_name));
   assert(raw.includes('guid = #'+item.name_guid));
   const parentFile=['rogue','hunter'].map(tree=>tree+'/game system data/juice/item/'+parent.internal_name+'.mitem').find(file=>Object.hasOwn(native,file));
   assert(parentFile);const parentRaw=nativeText(parentFile);
   assert(parentRaw.includes('ArmorItem '+parent.internal_name+' < uid='+item.parent_uid+' >'));
   if(item.uid==='4CDCE5B25BEEDAA50003373B98620D09')assert(!raw.includes('DZ_Scavenger'));
  }
  const source={...brand,members,ordinary_models:members,named_records:[]};
  const before=JSON.stringify(source),result=filterBrand(source);
  assert.equal(JSON.stringify(source),before);
  assert.deepEqual(result.members,members.filter(item=>!reviewed.has(item.uid)));
  assert.deepEqual(result.ordinary_models,result.members);
  assert.equal(result.excluded_salvaged_members.length,selected.length);
  assert(result.excluded_salvaged_members.every(item=>item.parent_uid&&item.reason===policy.reason));
  assert.deepEqual(filterBrand(result),result);
  removed+=result.excluded_salvaged_members.length;changed++;
 }
 assert.equal(removed,29);assert.equal(changed,15);
});

test('existing generation inputs retain every other field, named record and crafting relation',()=>{
 const before=JSON.stringify(input);let removed=0;
 for(const brand of input.brands){
  const result=filterBrand(brand);
  const control=filterBrand({...brand,members:brand.members.filter(item=>!reviewed.has(item.uid)),
   ordinary_models:brand.ordinary_models.filter(item=>!reviewed.has(item.uid))});
  const {excluded_salvaged_members:excluded,...retained}=result;
  assert.deepEqual(retained,control);
  assert.deepEqual(filterBrand(result),result);
  removed+=(excluded||[]).length;
 }
 assert.equal(removed,25);assert.equal(JSON.stringify(input),before);
});

test('unreviewed vendor items, matching display names, replicas and named items remain',()=>{
 const excluded=policy.models.find(item=>item.internal_name==='player_gear_holster_c_02_vendor');
 const parent={uid:excluded.parent_uid,internal_name:'player_gear_holster_c_02',name:{zh:'贾本汉腿挂包'}};
 const replica={uid:'replica',internal_name:'player_gear_holster_c_crafted_01',blueprint:{uid:'recipe',crafted_item_uid:'replica'}};
 const sameName={uid:'same-name',internal_name:'other_vendor',name:{zh:'回收的贾本汉腿挂包',en:'Salvaged Jaivardhan Thigh Rig'},tags:['DZ_Scavenger']};
 const unreviewed={uid:'4CDCE5B25BEED4D3000336F9308E8BDE',internal_name:'player_gear_back_d_02_vendor'};
 const named={uid:'named',internal_name:'named_vendor',name:sameName.name,is_named:true};
 const ordinary=[excluded,parent,replica,sameName,unreviewed];
 const result=filterBrand({title:excluded.brand,members:[...ordinary,named],ordinary_models:ordinary,named_records:[named]});
 assert.deepEqual(result.ordinary_models,[parent,replica,sameName,unreviewed]);
 assert.deepEqual(result.members,[parent,replica,sameName,unreviewed,named]);
 assert.deepEqual(result.named_records,[named]);assert.equal(result.ordinary_models[1].blueprint,replica.blueprint);
});

test('conflicting native identity or named classification blocks exclusion',()=>{
 const item=policy.models[0];
 assert.throws(()=>filterBrand({members:[{...item,internal_name:'other'}]}),/SALVAGED_MODEL_IDENTITY_MISMATCH/);
 assert.throws(()=>filterBrand({members:[{...item,is_named:true}]}),/SALVAGED_ORDINARY_MODEL_CLASSIFICATION_CONFLICT/);
 assert.throws(()=>filterBrand({named_records:[item]}),/SALVAGED_ORDINARY_MODEL_CLASSIFICATION_CONFLICT/);
});
