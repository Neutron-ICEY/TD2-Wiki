'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const ROOT=path.resolve(__dirname,'..');
function raw(root,file){return JSON.parse(fs.readFileSync(path.join(root,file),'utf8'));}
function registry(root=ROOT){return raw(root,'publishing/registry.json').entries;}
function fileTitle(row) {
  return row.title.split(':').slice(1).join(':');
}
function addressIndex(root) {
  const pages = new Map(), assets = new Map();
  for (const row of registry(root)) {
    let index, key;
    if (row.kind === 'pages') { index = pages; key = row.related_entity; }
    else if (row.kind === 'assets') { index = assets; key = row.id; }
    else continue;
    index.set(key, index.has(key) ? null : row);
  }
  function unique(index, id, error) {
    const row = index.get(id);
    assert.ok(row, error + ': ' + id);
    return row;
  }
  return {
    page: id => unique(pages, id, 'PAGE_IDENTITY_NOT_UNIQUE'),
    asset: id => unique(assets, id, 'ASSET_IDENTITY_NOT_UNIQUE')
  };
}
function page(id, root=ROOT) { return addressIndex(root).page(id); }
function asset(id, root=ROOT) { return addressIndex(root).asset(id); }
function display(e) { return e.fields.套装全称 || e.fields.装备组名称 || e.fields.装备名称 || ''; }

function read(root, file, data=raw(root,file)) {
  let addresses, published;
  function current() { return addresses ??= addressIndex(root); }
  function publishedFiles() {
    if (!published) {
      const file = 'publishing/baseline.json';
      const rows = fs.existsSync(path.join(root, file)) ? raw(root, file).entries : [];
      published = new Set(rows.filter(row => row.namespace === 6).map(fileTitle));
    }
    return published;
  }
  function walk(value) {
    if (Array.isArray(value)) return value.map(walk);
    if (!value || typeof value !== 'object') return value;
    const result = Object.fromEntries(Object.entries(value)
      .filter(([key]) => key !== 'asset_ref').map(([key, entry]) => [key, walk(entry)]));
    if (value.asset_ref) {
      const row = current().asset(value.asset_ref);
      result.wiki_file = fileTitle(row);
      result.confirmed_on_wiki = publishedFiles().has(result.wiki_file);
      result.local_available = fs.existsSync(path.join(root, row.source));
    }
    return result;
  }
  if (file === 'data/equipment/records.json') {
    for (const [id, entity] of Object.entries(data.entities)) {
      const row = current().page(id);
      Object.assign(entity, {source: row.source, page_title: row.title, page_id: row.id});
    }
    return data;
  }
  if (file === 'data/gear-sets/sets.json') {
    const records = raw(root, 'data/equipment/records.json').entities;
    const catalog = walk(data);
    for (const entity of catalog.sets) {
      const row = current().page(entity.id);
      Object.assign(entity, {source: row.source, title: display(records[entity.id]), page_title: row.title});
    }
    return catalog;
  }
  return walk(data);
}
function stored(database){const d=structuredClone(database);for(const e of Object.values(d.entities)){delete e.source;delete e.page_title;delete e.page_id;}return d;}
module.exports={registry,page,asset,display,read,raw,stored};
