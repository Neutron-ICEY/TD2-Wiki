const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const records=require('../tools/equipment/database.cjs').load(),native=require('../tools/equipment/crafting.cjs').load();
const projection=require('../tools/equipment/acquisition.cjs'),catalog=JSON.parse(fs.readFileSync('data/brand-sets/acquisition-methods.json','utf8'));
const facts=projection.build(native,records,catalog),bearUid='B00501356A8FE11300037E60A33CDC61',bear='exotic:'+bearUid.toLowerCase();
const retaliation=Object.entries(catalog.blueprint_source_rules).filter(([,r])=>r.preset==='retaliation');

test('retaliation requires the actual faction, action and awarded recipe',()=>{
  const data=structuredClone(native),uid='F46C7DF269A97B670003754BB6730040';
  const result=projection.resolve(data,records,catalog);
  const routes=result.byTarget[uid].filter(r=>r.kind==='retaliation_blueprint');
  assert(routes.some(r=>r.text==='成功保卫领土有几率获得 [报复行动：黯牙]'));
  const gaps=data.source_contexts.retaliation_blueprint.unresolved;
  assert(gaps.some(r=>r.faction_uid==='6B33C8FE592EB270000161655383C68D'&&r.action==='kill_squad'));
  const hint=retaliation.find(([,r])=>r.faction==='鬣狗'&&r.action==='kill_squad')[0];
  const candidates=Object.entries(data.blueprints).filter(([,bp])=>bp.source_refs.includes(hint));
  assert(candidates.length);
  for(const [target] of candidates)assert(!result.byTarget[target]?.some(r=>r.text.includes('鬣狗')&&r.text.includes('杀戮小队')));
  assert(!Object.values(facts).some(f=>f.equipment.some(r=>r.text.includes('报复行动'))));
});

test('a newly imported recipe reuses the faction grant only when its UID is awarded',()=>{
  const data=structuredClone(native),uid='F'.repeat(32),base='F46C7DF269A97B670003754BB6730040';
  data.blueprints[uid]={...structuredClone(data.blueprints[base]),name:'TEST blueprint'};
  assert(!projection.resolve(data,records,catalog).byTarget[uid]?.length);
  const route=Object.values(data.routes.retaliation_blueprint).find(r=>r.targets.includes(base));
  route.targets.push(uid);
  assert(projection.resolve(data,records,catalog).byTarget[uid].some(r=>r.kind==='retaliation_blueprint'));
  delete route.runtime_witnesses;
  assert(!projection.resolve(data,records,catalog).byTarget[uid]?.length);
});

function withReplay(){
  const data=structuredClone(native);
  data.source_contexts.legacy_manhunts[catalog.confirmed_equipment_sources[bearUid].climax_uid]={level:40};
  return data;
}

test('manhunt formatting preserves the supplied full name and condition without inventing Master or drop guarantees',()=>{
  const data=withReplay(),config=structuredClone(catalog),fact=config.confirmed_equipment_sources[bearUid];
  fact.mission='TEST 完整任务名称：目标';fact.condition='完成任务有几率获得';
  const after=projection.build(data,records,config);
  assert.deepEqual(after[bear].equipment,[{category:'mission',text:'TEST 完整任务名称：目标 - 完成任务有几率获得'}]);
  for(const id of Object.keys(facts))if(id!==bear)assert.deepEqual(after[id],facts[id]);
  delete config.confirmed_equipment_sources[bearUid];
  assert.deepEqual(projection.build(data,records,config)[bear].equipment,
    [{category:'mission',text:'华盛顿国际机场：鲍比·古兹曼 - 任务结算奖励'}]);
});

test('first-clear Master wording is required for every manhunt mission without name-specific exceptions',()=>{
  for(const mission of ['华盛顿国际机场：鲍比·古兹曼','TEST 另一猎捕任务：目标']){
    const data=withReplay(),config=structuredClone(catalog),rule=config.confirmed_equipment_sources[bearUid];
    rule.mission=mission;rule.condition='首次通关大师难度必定获得';
    const after=projection.build(data,records,config);
    assert.deepEqual(after[bear].equipment,[{category:'mission',text:mission+' - 首次通关大师难度必定获得'}]);
    assert.deepEqual(after[bear].blueprint,facts[bear].blueprint);
    rule.condition='大师难度必定获得';
    assert.throws(()=>projection.build(data,records,config),/ACQUISITION_PRESET.*首次通关大师难度必定获得/);
    delete config.confirmed_equipment_sources[bearUid];
    Object.assign(config.native_route_rules.airport_climax_reward,{mission,condition:'大师难度必定获得'});
    assert.throws(()=>projection.build(data,records,config),/ACQUISITION_PRESET.*首次通关大师难度必定获得/);
  }
});

test('reviewed native manhunt sources are scoped to four equipment UIDs and never add blueprint rewards',()=>{
  const expected={
    B0050135668E79E60005319DC2F2754C:'航天局总部：狄奥·帕内尔',
    B0050135678535F3000383BD7B7AC839:'罗斯福岛：亚兰妮·凯尔索',
    B005013567F671C000036FF025B589BD:'波托马克活动中心：经理',
    B005013568EE1608002429906813A622:'潮汐之潭猎捕：峰会'
  };
  const config=structuredClone(catalog),ids=new Set();
  for(const [uid,mission]of Object.entries(expected)){
    const id='exotic:'+uid.toLowerCase();ids.add(id);
    assert.equal(config.confirmed_equipment_sources[uid].evidence_type,'native_chain_review');
    assert.deepEqual(facts[id].equipment.filter(r=>r.category==='mission'),
      [{category:'mission',text:mission+' - 首次通关大师难度必定获得'}]);
    delete config.confirmed_equipment_sources[uid];
  }
  const without=projection.build(native,records,config);
  for(const [id,row]of Object.entries(facts)){
    assert.deepEqual(without[id].blueprint,row.blueprint);
    if(ids.has(id))assert.deepEqual(without[id].equipment,row.equipment.filter(r=>r.category!=='mission'));
    else assert.deepEqual(without[id],row);
  }
});

test('incomplete or ambiguous presets fail instead of silently producing acquisition text',()=>{
  for(const edit of [{preset:'unknown'},{mission:''},{condition:''},{text:'conflicting text'}]){
    const config=structuredClone(catalog);Object.assign(config.confirmed_equipment_sources[bearUid],edit);
    assert.throws(()=>projection.build(native,records,config),/ACQUISITION_PRESET/);
  }
  for(const edit of [{action:'unknown'},{faction:''},{text:'conflicting text'}]){
    const config=structuredClone(catalog);Object.assign(config.blueprint_source_rules[retaliation[0][0]],edit);
    assert.throws(()=>projection.build(native,records,config),/ACQUISITION_PRESET/);
  }
});
