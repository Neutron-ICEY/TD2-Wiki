const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(process.argv[2] || path.resolve(__dirname, '../..'));
const parser = require(path.join(root, 'ui/editor/src/parser.js'));
const registry = JSON.parse(fs.readFileSync(path.join(root, 'publishing/registry.json'), 'utf8'));
const database = require('../equipment/database.cjs').load(root);
const effectCatalog = require('../equipment/database.cjs').references(database);
const baseline = JSON.parse(fs.readFileSync(path.join(root, 'publishing/baseline.json'), 'utf8'));
const pending=JSON.parse(fs.readFileSync(path.join(root,'publishing/pending-moves.json'),'utf8')).entries;
const published = new Set(baseline.entries.filter(row => row.namespace === 0 && row.revision_id > 0).map(row => row.title));
const pages = registry.entries.filter(row => row.source.startsWith('wiki/pages/brands/') && row.namespace === 0 && published.has(pending.find(m=>m.id===row.id)?.from_title||row.title));
const records = pages.map(row => {
  const raw = fs.readFileSync(path.join(root, row.source), 'utf8');
  const main = parser.parse(raw, {textEnvelope: true}).main;
  function fields(node) {
    return Object.fromEntries(node.segments.filter(s => s.equal !== null).map(s =>
      [raw.slice(s.start, s.equal).trim(), raw.slice(s.equal + 1, s.end).trim()]));
  }
  const params=fields(main),entity=database.entities[params.资料ID];
  if(!entity||entity.source!==row.source)throw new Error('Brand navigation identity mismatch');
  const notes=main.segments.flatMap(s => s.nested).filter(n => n.name === '品牌装备摘要').map(fields);
  const projection=require('../equipment/projection.cjs');
  const named=projection.named(entity).map(r=>({...notes.find(n=>n.stable_id===r.stable_id),...r,
    talent_icon:r.talent_mode==='fixed'?entity.effects.find(e=>e.效果ID===r.天赋引用&&e.模式==='PvE')?.图标:''}));
  return {id:row.related_entity,title: row.title, source: row.source, params:{...params,...projection.parameters(entity,params.资料ID)}, named};
});
const collator = new Intl.Collator('zh-Hans-CN-u-co-pinyin', {usage: 'sort', sensitivity: 'variant'});
const namedOrder = records.flatMap(page => page.named).sort((a, b) => collator.compare(a['装备名称'], b['装备名称'])).map(item => item.stable_id);
const exotics = registry.entries.filter(row => row.namespace === 0 && row.related_entity?.startsWith('exotic:') && published.has(pending.find(m=>m.id===row.id)?.from_title||row.title)).map(row => {
  const raw = fs.readFileSync(path.join(root, row.source), 'utf8');
  const main = parser.parse(raw, {textEnvelope: true}).main;
  if(main.name !== '奇特装备信息') throw new Error('Exotic navigation requires its canonical template');
  const params = Object.fromEntries(main.segments.filter(s => s.equal !== null).map(s => [raw.slice(s.start,s.equal).trim(),raw.slice(s.equal+1,s.end).trim()]));
  if(params.资料ID !== row.related_entity) throw new Error('Exotic navigation identity mismatch');
  Object.assign(params,require('../equipment/projection.cjs').parameters(database.entities[params.资料ID],params.资料ID));
  const effects=require('../../ui/editor/src/page-effects.js');
  return {title:row.title,params,effects:effects.resolve(effects.read(params['效果资料']||''),effectCatalog)};
}).sort((a,b)=>collator.compare(a.params['装备名称'],b.params['装备名称']));
process.stdout.write(JSON.stringify({pages: records, named_order: namedOrder, exotics}));
