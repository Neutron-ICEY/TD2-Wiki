const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const records=require('../tools/equipment/database.cjs').load(),native=require('../tools/equipment/crafting.cjs').load();
const projection=require('../tools/equipment/acquisition.cjs');
const catalog=JSON.parse(fs.readFileSync('data/brand-sets/acquisition-methods.json','utf8'));
const facts=projection.build(native,records,catalog);
const identity=name=>Object.keys(records.entities).find(id=>require('../tools/identity.cjs').display(records.entities[id])===name);

test('recurring event evidence is independent of the archived limited caches',()=>{
  const uid='B005013567B5935200036DD2A7E091D1',turmoil=facts[native.items[uid].record_id];
  assert.deepEqual(turmoil.equipment,[{category:'event',text:'活动获取'}]);
  const config=structuredClone(catalog);delete config.confirmed_equipment_sources[uid];
  assert.deepEqual(projection.build(native,records,config)[native.items[uid].record_id].equipment,[]);
  assert.deepEqual(turmoil.blueprint,[]);
  assert(Object.values(native.routes.season_weapon_cache).some(r=>r.targets.includes(uid)));
  const ravenous=facts[identity('饥饿之人')];
  assert(ravenous.equipment.some(r=>r.text==='铁驹行动 - 开启最终奖励箱 [10%]'));
  assert(ravenous.blueprint.some(r=>r.text.includes('制作图纸')&&r.text.includes('成功保卫领土')));
  assert(ravenous.blueprint.some(r=>r.text.includes('重新配置图纸')&&r.text.includes('持有饥饿之人')));
  assert(!Object.values(facts).some(f=>f.equipment.some(r=>/Y\d+S\d+|威望扩展目标/.test(r.text))));
});

test('signature weapons expose only their native specialization grants; unreleased UIDs are excluded',()=>{
  const all=Object.values(records.entities).flatMap(e=>e.collections?.武器型号资料?.rows||[]).map(r=>r.data);
  const signatures=all.filter(r=>r.kind==='signature');
  assert.equal(signatures.length,6);
  const nativeSources=require('../tools/equipment/source-relations.cjs').build(native,records);
  for(const r of signatures){
    const id=native.items[r.装备UID].entity_id;
    assert(nativeSources[id].some(s=>s.kind==='specialization_signature'&&s.confirmable&&s.target===r.装备UID));
    assert.deepEqual(facts[id],{equipment:[{category:'specialization',text:r.specialization.name+'专长解锁'}],blueprint:[],hasBlueprint:false});
  }
  const excluded=require('../data/equipment/native-map.json').unreleased_items||{};
  for(const uid of Object.keys(excluded)){
    assert(!native.items[uid]);
    assert(!all.some(r=>r.装备UID===uid||r.variants?.some(v=>v.uid===uid)));
    assert(!facts['weapon_'+uid.toLowerCase()]);
  }
});

test('the named Mk16 Malinois has a verified limited project reward and no established regular grant or recipe',()=>{
  const uid='B00501356AC76687000382F9030622D0',item=native.items[uid];
  assert.equal(item.name,'玛伦牧羊犬');
  assert.equal(item.kind,'named');
  const models=records.entities[item.entity_id].collections.武器型号资料.rows.map(r=>r.data);
  assert(models.some(r=>r.装备UID===uid&&r.kind==='named'));
  assert(models.some(r=>r.kind==='normal'&&r.装备名称==='Mk16'));
  assert.equal(catalog.confirmed_equipment_sources[uid].availability,'limited');
  const result=projection.resolve(native,records,catalog);
  assert(result.excluded[uid].some(r=>r.kind==='observation'&&r.status==='limited'));
  assert.deepEqual(result.facts[item.record_id],{equipment:[],blueprint:[],hasBlueprint:false});
});

test('Lullaby vendor and entitlement resolve different blueprint UIDs',()=>{
  const weapon='4CDCE5B25C5C484A00032712FD0BAB66',id=native.items[weapon].entity_id;
  const conversion='4CDCE5B25C125A5A00032047378F37E0',reconfigure='4CDCE5B25C45DB700003F7D4D3E5D740';
  assert.equal(native.blueprints[conversion].purpose,'conversion');
  assert.equal(native.blueprints[reconfigure].purpose,'reconfigure');
  const relations=require('../tools/equipment/source-relations.cjs').build(native,records)[id];
  assert.deepEqual(relations.filter(r=>r.confirmable&&r.kind==='vendor').map(r=>r.target),[reconfigure]);
  assert.deepEqual(relations.filter(r=>r.confirmable&&r.kind==='lullaby_pack').map(r=>r.target),[conversion]);
  assert.equal(native.items[native.blueprints[conversion].input_uid].name,'美梦');
  assert(facts[id].equipment.some(r=>r.text==='制作台外观转换 [需要美梦]'));
  assert(!facts[id].equipment.some(r=>r.text==='制作台制作'));
  assert(facts[id].blueprint.some(r=>r.category==='vendor'&&r.text.includes('重新配置图纸')));
  assert(facts[id].blueprint.some(r=>r.category==='entitlement'&&r.text.includes('外观转换图纸')));

});

test('cache alternatives and vendor ownership conditions combine only for the same grant',()=>{
  const investor=identity('投资者'),nurse=identity('护士护膝'),liberty=identity('自由'),catharsis=identity('净化');
  const reconfigure=id=>facts[id].blueprintGroups.find(g=>g.title==='重新配置图纸').methods;
  assert.deepEqual(reconfigure(investor),['依娜亚出售 [持有投资者或护士护膝]']);
  assert.deepEqual(reconfigure(nurse),['暂无获取资料']);
  assert.deepEqual(facts[nurse].blueprint,[]);
  assert(!facts[nurse].equipment.some(r=>r.category==='craft'));
  assert.deepEqual(facts[catharsis].equipment.filter(r=>r.category==='cache'),[{category:'cache',text:'奇特贮藏箱'}]);
  assert.deepEqual(facts[liberty].equipment.filter(r=>r.category==='cache'),[{category:'cache',text:'奇特贮藏箱 [持有肯卓的自由设计图]'}]);
  const data=structuredClone(native),maskUid='B3CF2E92615AB3C60003639A6C96F424';
  for(const route of Object.values(data.routes.exotic_cache)){
    if(!JSON.stringify([route.conditions,route.parent_conditions]).includes('myRequiredItemType'))
      route.targets=route.targets.filter(uid=>uid!==maskUid);
  }
  assert(projection.build(data,records,catalog)[catharsis].equipment.some(r=>r.text==='奇特贮藏箱 [持有净化：改装配置]'));
});

test('alternative vendor entries cannot turn a conjunction or a negated condition into standalone ownership',()=>{
  const data=structuredClone(native),target='B005013569AEC73B000917C79B3C8D9B',id=identity('投资者');
  const routes=Object.values(data.routes.vendor).filter(r=>r.targets.includes(target));
  const nurse=routes.find(r=>JSON.stringify(r.conditions).includes('player_gear_kneepads_exotic_05'));
  nurse.parent_conditions={type:'LootConditionIsInDarkZone',properties:['myIsNegated TRUE'],children:[]};
  const groups=projection.build(data,records,catalog)[id].blueprintGroups;
  const methods=groups.find(g=>g.title==='重新配置图纸').methods;
  assert(methods.includes('依娜亚出售 [持有投资者]'));
  assert(methods.some(t=>t.includes('非（位于暗区）')&&t.includes('持有护士护膝')));
  assert(!methods.some(t=>t.includes('投资者或护士护膝')));
});

test('unavailable weapon recipes do not appear as player blueprints or crafting sources',()=>{
  const weapons=require('../tools/equipment/weapons.cjs');
  for(const [blueprint,{target}] of Object.entries(catalog.unavailable_blueprints)){
    const item=native.items[target],entity=records.entities[item.entity_id];
    assert(native.blueprints[blueprint].targets.includes(target));
    const model=weapons.rows(entity).find(r=>r.装备UID===target);
    const fact=facts[model.kind==='named'?model.stable_id:item.entity_id];
    assert.deepEqual(model.blueprints,[]);
    assert.equal(fact.hasBlueprint,false);
    assert.deepEqual(fact.blueprint,[]);
    assert(!fact.equipment.some(row=>row.category==='craft'));
  }
});

test('G28 and Stinger remain craftable with an owned recipe while no current recipe grant is shown',()=>{
  const blueprint=native.blueprints.E03CE5EA63A073EC000366E60BFE1C77;
  const item=native.items[blueprint.targets[0]],fact=facts[item.entity_id];
  assert.equal(item.name,'G28');
  assert(catalog.confirmed_blueprint_sources.E03CE5EA63A073EC000366E60BFE1C77.text.includes('37 级'));
  assert.deepEqual(fact.blueprint,[]);assert(fact.equipment.some(r=>r.category==='craft'));
  assert(!fact.equipment.some(row=>row.text.includes('37 级')));
  const stinger='4CDCE5B25D8346FA0003491FFA372A61',itemId=native.items[native.blueprints[stinger].targets[0]].record_id;
  assert.deepEqual(facts[itemId].equipment,[{category:'craft',text:'制作台制作'}]);
  assert.deepEqual(facts[itemId].blueprint,[]);
  const config=structuredClone(catalog);delete config.confirmed_blueprint_sources[stinger].usable_if_owned;
  assert.deepEqual(projection.build(native,records,config)[itemId].equipment,[]);
});

test('a dated recipe grant qualifies its bench output after the season starts, without restoring its recipe source',()=>{
  const uid='346395BC5F19593F0003AEB999A97C43',target=native.blueprints[uid].targets[0];
  const data=structuredClone(native);
  const windows=Object.values(data.routes.season_blueprint).filter(r=>r.targets.includes(uid));
  assert(windows.length>0);
  const check=()=>{
    const {byTarget}=projection.resolve(data,records,catalog);
    assert(!byTarget[uid]?.length);
    return (byTarget[target]||[]).some(r=>r.kind==='craft'&&r.entry===uid);
  };
  assert(check());
  for(const route of windows)route.active_time='"2099-01-01 08:00:00 to 2099-04-01 07:59:59"';
  assert(!check());
  for(const route of windows)delete route.active_time;
  assert(!check());
});

test('a dated cache and a standing cache can share a window while only the supplied UID qualifies',()=>{
  const data=structuredClone(native),uid=catalog.native_route_rules.named_cache.entry_uid;
  assert(data.source_contexts.cache_windows[uid].length);
  const initial=projection.resolve(data,records,catalog);
  const item=Object.values(data.routes.named_cache).flatMap(r=>r.targets).find(t=>initial.byTarget[t]?.some(r=>r.kind==='named_cache'));
  const target=()=>projection.resolve(data,records,catalog).byTarget[item]||[];
  assert(target().some(r=>r.kind==='named_cache'));
  const stock=data.source_contexts.cache_supply[uid];
  data.source_contexts.cache_supply[uid]=[];
  assert(!target().some(r=>r.kind==='named_cache'));
  data.source_contexts.cache_supply[uid]=stock.map(s=>({...s,availability:'season_slot'}));
  assert(!target().some(r=>r.kind==='named_cache'));
  const currentSeason=Object.keys(native.source_contexts.cache_supply).filter(k=>native.source_contexts.cache_supply[k].some(s=>s.availability==='season_slot'));
  assert(currentSeason.length);
  assert(!Object.values(facts).some(f=>f.equipment.some(r=>r.text==='红色地平线贮藏箱')));
});

test('recurring progression boxes resolve their own tables and the distinct source types',()=>{
  const rows=Object.values(native.routes.regular_cache);
  assert(rows.some(r=>r.display_text==='暗区精通贮藏箱'&&r.source.endsWith('ltdrp_sealed_cache_level_up_darkzone.mloottable')));
  assert(rows.some(r=>r.display_text==='冲突战贮藏箱'&&r.item_list.endsWith('itemlist_equipment_pvp_cache.rejuice')));
  assert(!rows.some(r=>r.display_text==='优化贮藏箱'));
  const activity=Object.values(native.routes.world_activity);
  assert(activity.some(r=>r.display_text==='宣传广播'&&r.runtime_witnesses[0].flag_uid));
  assert(activity.some(r=>r.display_text==='公开处决'&&r.pool_uid===activity[0].pool_uid));
});

test('every route keeps its condition and different permanent mechanisms are separate rows',()=>{
  const death=facts.gear_511_deathgrips;
  for(const label of ['暗区战利品掉落','具名贮藏箱','制作台制作'])
    assert(death.equipment.some(r=>r.text===label),label);
  assert(!death.equipment.some(r=>r.text==='战利品掉落'));
  assert(death.blueprint.some(r=>r.text==='重建贮藏箱'));
  const golan=facts[identity('戈兰装备有限公司')];
  for(const text of ['战利品掉落','暗区战利品掉落','商人轮换出售'])
    assert(golan.equipment.some(r=>r.text===text),text);
  assert.deepEqual(golan.blueprint.map(r=>r.text),['完成计划','完成高峰大厦挑战','接管警戒等级3以上的控制点','依娜亚出售']);
  for(const info of Object.values(facts))for(const purpose of ['equipment','blueprint']){
    assert.equal(new Set(info[purpose].map(r=>r.text)).size,info[purpose].length);
    for(const row of info[purpose]){
      assert.deepEqual(Object.keys(row),['category','text']);assert(projection.categories[purpose][row.category]);
      assert(!/source_|[a-f0-9]{32}|需拥有对应图纸|；/.test(row.text));
    }
  }
});

test('public rules accept new reliable members without per-item confirmation',()=>{
  const data=structuredClone(native),id='gear_511_keeper',uid=Object.keys(data.items).find(uid=>data.items[uid].record_id===id),route=Object.values(data.routes.named_cache)[0];
  route.targets=route.targets.filter(t=>t!==uid);assert(!projection.build(data,records,catalog)[id].equipment.some(r=>r.text==='具名贮藏箱'));
  route.targets.push(uid);assert(projection.build(data,records,catalog)[id].equipment.some(r=>r.text==='具名贮藏箱'));
  route.entry_uid='A'.repeat(32);assert(!projection.build(data,records,catalog)[id].equipment.some(r=>r.text==='具名贮藏箱'));
  assert(!Object.hasOwn(catalog,'source_assessments'));assert(!Object.hasOwn(catalog,'shared_rules'));
});

test('disabled cache and vendor groups cannot select categories or fall back to source hints',()=>{
  const sources=require('../tools/equipment/source-relations.cjs');
  for(const kind of ['exotic_cache','reconstructed_cache','vendor']){
    const data=structuredClone(native),rule=catalog.native_route_rules[kind];
    const affected=Object.entries(sources.build(data,records)).filter(([,rows])=>rows.some(r=>r.kind===kind&&r.confirmable)).map(([id])=>id);
    assert(affected.length>0);
    for(const route of Object.values(data.routes[kind]))route.entry_scope='disabled';
    const relations=sources.build(data,records),after=projection.build(data,records,catalog,relations);
    assert(!Object.values(relations).flat().some(r=>r.kind===kind&&r.confirmable));
    for(const id of affected)assert(!after[id][rule.purpose].some(r=>r.text.includes(rule.text)),kind+'/'+id);
    if(kind==='vendor'){
      const uid=Object.values(data.routes.vendor).flatMap(r=>r.targets).find(uid=>data.blueprints[uid].source_refs.some(ref=>
        catalog.blueprint_source_rules[ref]?.category==='vendor'&&data.sources[ref].verification==='current_confirmed'));
      assert(uid,'The regression must cover a confirmed generic vendor hint');
    }
  }
});

test('closed drop entries preserve established families and isolate dedicated gear set routes',()=>{
  const unclosed='set:b00501356a9699cc0007e4333064010a';
  assert(records.entities[unclosed]);
  for(const [id,entity]of Object.entries(records.entities))if(entity.source.startsWith('wiki/pages/brands/')||entity.template==='装备组信息'){
    if(id===unclosed){
      assert(facts[id].equipment.some(r=>r.text.includes('守护者')));
      assert(facts[id].equipment.some(r=>r.text.includes('中央公园')));
      assert(!facts[id].equipment.some(r=>r.category==='drop'));
    }else assert(facts[id].equipment.some(r=>r.category==='drop'),entity.source);
  }
  const hunter='gear_bfaaa1fc5e1f1f19000513b8c060e9ab';
  assert.deepEqual(facts[hunter].equipment.map(r=>r.text),['避风港猎人箱','猎人箱解锁后可在卡西购买','制作台制作']);
  assert.deepEqual(facts[hunter].blueprint,[{category:'vendor',text:'猎人箱解锁后依娜亚出售'}]);
  const data=structuredClone(native);
  for(const kind of ['common_gear_pool','targeted_slot','targeted_brand','targeted_gearset','world_activity'])for(const row of Object.values(data.routes[kind]))delete row.runtime_witnesses;
  const guarded=projection.build(data,records,catalog);
  assert(!guarded[identity('戈兰装备有限公司')].equipment.some(r=>r.category==='drop'));
  assert.deepEqual(guarded[hunter],facts[hunter]);
  data.routes.hunter_cache={};data.routes.hunter_vendor={};
  assert(!projection.build(data,records,catalog)[hunter].equipment.some(r=>r.text.includes('猎人箱')));
});

test('observed equipment sources require UID and evidence without changing native or blueprint routes',()=>{
  const uid='B00501356A96AE0E0009BCFE54AFCA07',id='gear_'+uid.toLowerCase();
  assert.match(facts[id].equipment[0].text,/彩蛋猎人.*钥匙.*猎人箱/);
  const without=projection.build(native,records,{...catalog,confirmed_equipment_sources:{}});
  assert.deepEqual(without[id].equipment,[]);assert.deepEqual(without[id].blueprint,facts[id].blueprint);
  for(const confirmed_equipment_sources of [{[uid]:{...catalog.confirmed_equipment_sources[uid],evidence:[]}},
      {[uid]:{...catalog.confirmed_equipment_sources[uid],verification:'native_only'}},
      {[uid]:{...catalog.confirmed_equipment_sources[uid],entry_uid:'invalid'}},
      ['A'.repeat(32)].reduce((o,k)=>({...o,[k]:catalog.confirmed_equipment_sources[uid]}),{})]){
    assert.throws(()=>projection.build(native,records,{...catalog,confirmed_equipment_sources}),/EQUIPMENT_CURRENT_EVIDENCE/);
  }
});

test('a mission or guardian pool needs a live entry and a satisfied reward branch',()=>{
  const data=structuredClone(native),apex='set:b00501356a9699cc0007e4333064010a';
  for(const kind of ['guardian_drop','pearl_reward'])for(const row of Object.values(data.routes[kind]))delete row.runtime_witnesses;
  const after=projection.build(data,records,catalog);
  assert(!after[apex].equipment.some(r=>/守护者|中央公园/.test(r.text)));
  assert.deepEqual(after[apex].blueprint,facts[apex].blueprint);
});

test('a confirmed permanent Master reward does not depend on recognition of the replay by the importer',()=>{
  const uid='B00501356A8FE11300037E60A33CDC61',id='exotic:'+uid.toLowerCase(),data=structuredClone(native);
  const observed=catalog.confirmed_equipment_sources[uid];
  assert(observed.evidence.length);assert(facts[id].equipment.some(r=>r.text==='华盛顿国际机场：鲍比·古兹曼 - 首次通关大师难度必定获得'));
  data.source_contexts.legacy_manhunts[observed.climax_uid]={level:40};
  const unlocked=projection.build(data,records,catalog);
  assert(unlocked[id].equipment.some(r=>r.text.includes('首次通关大师难度必定获得')));
  const config=structuredClone(catalog);delete config.confirmed_equipment_sources[uid];
  const nativeOnly=projection.build(data,records,config);
  assert(nativeOnly[id].equipment.some(r=>r.text.includes('任务结算奖励')));
  assert(!nativeOnly[id].equipment.some(r=>r.text.includes('首次通关大师难度必定获得')));
  const unresolved=Object.values(native.routes.airport_climax_reward).filter(r=>r.entry_scope==='pool');
  assert.equal(unresolved.length,2);
  for(const row of unresolved)assert.match(JSON.stringify(row.conditions),/LootConditionIsPlayerPersistentFlagValue/);
  assert.deepEqual(unlocked[id].blueprint,facts[id].blueprint);
});

test('a manual reward supersedes only its exact equipment and entry pair',()=>{
  const uid='B00501356A8FE11300037E60A33CDC61',id='exotic:'+uid.toLowerCase(),data=structuredClone(native),config=structuredClone(catalog);
  const rule=config.confirmed_equipment_sources[uid];
  data.source_contexts.legacy_manhunts[rule.climax_uid]={level:40};
  const other=Object.keys(data.items).find(k=>data.items[k].record_id==='gear_511_keeper');
  for(const row of Object.values(data.routes.airport_climax_reward))row.targets.push(other);
  const after=projection.build(data,records,config);
  assert(after[id].equipment.some(r=>r.text.includes('首次通关大师难度必定获得')));
  assert(!after[id].equipment.some(r=>r.text.includes('任务结算奖励')));
  assert(after.gear_511_keeper.equipment.some(r=>r.text.includes('任务结算奖励')));
  rule.entry_uid='A'.repeat(32);
  assert(projection.build(data,records,config)[id].equipment.some(r=>r.text.includes('任务结算奖励')));
});

test('brand changes cannot alter named equipment or blueprint facts',()=>{
  const data=structuredClone(native),owner=identity('5.11 Tactical');
  for(const [uid,item]of Object.entries(data.items))if(item.entity_id===owner&&item.kind==='brand'){
    for(const bp of Object.values(data.blueprints))bp.targets=bp.targets.filter(t=>t!==uid);
  }
  const after=projection.build(data,records,catalog);assert.notDeepEqual(after[owner],facts[owner]);
  for(const row of records.entities[owner].collections.具名装备资料.rows)assert.deepEqual(after[row.stable_id],facts[row.stable_id]);
});

test('a source hint cannot repair a missing or disabled recipe grant',()=>{
  const uid='F46C7DF269A97B670003754BB6730040',id=identity('饥饿之人'),data=structuredClone(native);
  assert(facts[id].blueprint.some(r=>r.text.includes('黯牙')));
  data.routes.retaliation_blueprint={};
  for(const route of Object.values(data.routes.vendor))route.conditions={type:'UnknownRuntimeCondition'};
  const result=projection.resolve(data,records,catalog);
  assert(!result.byTarget[uid]?.length);
  assert(!result.facts[id].equipment.some(r=>r.category==='craft'));
  assert(!result.facts[id].blueprint.some(r=>r.category==='vendor'));
});

test('quest components select crafting recipes separately from their reconfiguration grants',()=>{
  for(const [name,kind,condition] of [
    ['自由','mission_boss_blueprint','准心和导轨'],
    ['复仇女神','mission_boss_blueprint','枪托、枪机或枪管之一'],
    ['话匣子','mission_cache_blueprint','鬣狗钥匙']
  ]){
    const row=Object.values(native.routes[kind]).find(r=>r.display_text.includes(condition));
    assert(row,name);assert.equal(native.blueprints[row.targets[0]].purpose,'craft');
    const fact=facts[identity(name)];
    assert(fact.blueprint.some(r=>r.text.startsWith('制作图纸 · ')&&r.text.includes(condition)));
    assert(fact.equipment.some(r=>r.text==='制作台制作'));
    assert(!fact.equipment.some(r=>r.text.includes(condition)));
    assert(fact.blueprint.some(r=>r.text.startsWith('重新配置图纸 · ')));
  }
});

test('catalog has no legacy manual acquisition records',()=>{
  assert(!Object.hasOwn(catalog,'preserved_sources'));
});

test('native ordering and editor labels do not change classification output',()=>{
  const data=structuredClone(native);
  for(const group of Object.values(data.routes))for(const route of Object.values(group)){route.targets.reverse();route.text='TEST native editor label';}
  data.routes=Object.fromEntries(Object.entries(data.routes).reverse());
  assert.deepEqual(projection.build(data,records,catalog),facts);
});

test('a settlement completion grants the blueprint and the specialization grid grants the weapon',()=>{
  const m4=facts[identity('警用 M4')],pistol=facts[identity('P320 XCompact')];
  assert(m4.blueprint.some(r=>r.text==='戏院聚落计划「冷冻贮存建设」'));
  assert(!m4.equipment.some(r=>r.text.includes('冷冻贮存建设')));
  assert(pistol.equipment.some(r=>r.text.includes('重机枪手专长解锁配枪')));
  assert.equal(pistol.blueprint.length,0);
});
