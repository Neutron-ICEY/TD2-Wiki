'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const identity = require('../tools/identity.cjs');
const {readerData} = require('../tools/exotic_gear/data.cjs');

test('an exotic icon receipt changes maintenance status but leaves generated Reader bytes and version identical', t => {
  const root = path.resolve(__dirname, '..');
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'td2-exotic-reader-'));
  t.after(() => fs.rmSync(fixture, {recursive:true, force:true}));
  for (const file of [
    'data/equipment/attributes.json', 'data/equipment/crafting.json',
    'data/brand-sets/minor-attributes.json', 'data/brand-sets/fixed-minor-presets.json',
    'data/brand-sets/equipment-base-rules.json', 'data/brand-sets/equipment-ui.json',
    'data/brand-sets/acquisition-methods.json', 'data/exotic-gear/talents.json', 'publishing/registry.json'
  ]) {
    const dest = path.join(fixture, file);
    fs.mkdirSync(path.dirname(dest), {recursive:true});
    fs.copyFileSync(path.join(root, file), dest);
  }
  const all = identity.raw(root, 'data/equipment/records.json');
  const [id, entity] = Object.entries(all.entities).find(([, value]) => value.template === '奇特装备信息');
  const records = {schema_version: all.schema_version, entities: {[id]: entity}};
  const save = (file, value) => fs.writeFileSync(path.join(fixture, file), JSON.stringify(value));
  save('data/equipment/records.json', records);
  const talentsFile = 'data/exotic-gear/talents.json';
  const icon = identity.raw(fixture, talentsFile).talents.find(t => t.icon?.asset_ref).icon;
  const asset = identity.asset(icon.asset_ref, fixture);
  const maintained = () => identity.read(fixture, talentsFile, icon).confirmed_on_wiki;
  save('publishing/baseline.json', {entries: []});
  assert.equal(maintained(), false);
  const before = readerData(fixture);
  save('publishing/baseline.json', {entries: [{namespace:6, title:asset.title}]});
  assert.equal(maintained(), true);
  assert.equal(readerData(fixture), before);
  assert.doesNotMatch(before, /confirmed_on_wiki|local_available/);
  const version = raw => raw.match(/\["version"\]="(equipment-[a-z0-9]+)"/)[1];
  entity.fields.简介 = '用于验证版本跟随资料内容变化';
  save('data/equipment/records.json', records);
  const after = readerData(fixture);
  assert.notEqual(version(before), version(after));
  assert.match(after, /用于验证版本跟随资料内容变化/);
  const talentCatalog = identity.raw(fixture, talentsFile);
  talentCatalog.talents.push(talentCatalog.talents[0]);
  save(talentsFile, talentCatalog);
  assert.throws(() => readerData(fixture), /EXOTIC_TALENT_ID/);
});
