const {test}=require('node:test'),assert=require('node:assert/strict');
const sources=require('../tools/equipment/source-relations.cjs');
const records=require('../tools/equipment/database.cjs').load(),native=require('../tools/equipment/crafting.cjs').load();

const has={type:'LootConditionHasItem',properties:['myRequiredItemType dye'],children:[]};
const level={type:'LootConditionLooterLevel',properties:['myLevel 40'],children:[]};
const tier={type:'LootConditionOpenWorldProgressionTier',properties:['myProgressionTier WorldTier1','myOperator GreaterThanOrEqual'],children:[]};
const names={dye:{name:'测试外观',uid:'A'.repeat(32)}};

test('conditions validate AND/OR, negation, ownership and level restrictions',()=>{
  for(const node of [has,level,tier,{type:'myConditions',children:[has,level]},{type:'ORCondition',properties:['myIsNegated TRUE'],children:[has,level]}]){
    assert.doesNotThrow(()=>sources.validateConditions(node,names));
  }
  assert.throws(()=>sources.validateConditions({type:'ORCondition',children:[]},names),/空的或条件/);
  assert.throws(()=>sources.validateConditions({type:'ORCondition',children:[has,{type:'UnknownRuntimeCondition'}]},names),/未解析/);
  assert.throws(()=>sources.validateConditions({...tier,properties:[...tier.properties,'myIsNegated UNKNOWN']},names),/否定值无效/);
  for(const node of [{...level,properties:['myLevel 40','myXPType Unknown']},{...level,properties:['myLevel 40','myLevel 30']},{...level,children:[has]},{type:'UnknownRuntimeCondition'},has]){
    assert.throws(()=>sources.validateConditions(node,{}),/未解析|无效/);
  }
});

test('vendor conditions remain attached to individual blueprint UIDs',()=>{
  const data=structuredClone(native),base=Object.values(data.routes.vendor).find(r=>r.targets.length>1),[a,b]=base.targets;
  data.routes.vendor={a:{...base,targets:[a],conditions:{...level,properties:['myLevel 30']}},b:{...base,targets:[b],conditions:level}};
  const rows=Object.values(sources.build(data,records)).flat().filter(r=>r.kind==='vendor');
  assert.equal(rows.length,2);assert(rows.every(r=>r.confirmable));
  data.routes.vendor.a.conditions={type:'UnknownRuntimeCondition'};
  const changed=Object.values(sources.build(data,records)).flat().filter(r=>r.kind==='vendor');
  assert(changed.some(r=>r.target===a&&!r.confirmable));assert(changed.some(r=>r.target===b&&r.confirmable));
});

test('unclosed routes, disabled targets, unknown parents and zero weights stay unknown',()=>{
  const data=structuredClone(native),route=Object.values(data.routes.named_cache)[0],uid=route.targets.find(uid=>data.items[uid].record_id==='gear_511_deathgrips');
  for(const patch of [{entry_scope:'pool'},{conditions:{type:'UnknownRuntimeCondition'}},{definition:{properties:['myDropWeight 0']}}]){
    const altered=structuredClone(data);altered.routes.named_cache={test:{...route,...patch}};
    assert(sources.build(altered,records).gear_511_deathgrips.filter(r=>r.kind==='named_cache').every(r=>!r.confirmable));
  }
  for(const value of [false,null]){const altered=structuredClone(data);altered.items[uid].obtainable=value;assert(sources.build(altered,records).gear_511_deathgrips.filter(r=>r.kind==='named_cache').every(r=>!r.confirmable));}
  const rows=Object.values(sources.build(data,records)).flat();
  for(const kind of ['direct_reward','project_reward']){
    assert(rows.some(r=>r.kind===kind));assert(rows.filter(r=>r.kind===kind).every(r=>!r.confirmable));
  }
  for(const kind of ['blueprint_reward_pool','summit_challenge_blueprint']){
    assert(rows.some(r=>r.kind===kind&&r.purpose==='blueprint'&&r.confirmable));
    for(const route of Object.values(data.routes[kind]))delete route.runtime_witnesses;
    assert(Object.values(sources.build(data,records)).flat().filter(r=>r.kind===kind).every(r=>!r.confirmable));
  }
});

test('named identity requires its own UID and never falls back to brand ownership',()=>{
  const data=structuredClone(native),uid=Object.keys(data.items).find(uid=>data.items[uid].record_id==='gear_511_deathgrips');
  assert.equal(sources.owner(data,records,uid),'gear_511_deathgrips');
  data.items[uid].record_id='unknown';assert.equal(sources.owner(data,records,uid),null);
});
