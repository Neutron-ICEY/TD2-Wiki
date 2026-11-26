'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const site = require('../ui/editor/src/site-session.js');
const {talentKey} = require('../ui/editor/src/page-fields.js');

const key = talentKey('effect-one', 'PVE');
const entity = {
  title: '样本', template: '奇特装备信息',
  talents: [{id: 'effect-one', mode: 'PVE', name: '旧名称'}, {id: 'effect-two', mode: 'PVP', name: '另一天赋'}]
};
async function open(extraFields = '') {
  const input = '{{奇特装备信息\n|资料ID=sample' + extraFields + '\n}}\n';
  const fixture = {catalog: {sample: structuredClone(entity)}, saves: [], reads: 0};
  let revision = {title: '样本', pageid: 1, revid: 1, raw: input};
  const adapter = {
    load: async () => ({...revision}),
    loadCatalog: async () => {
      fixture.reads++;
      if (fixture.failure) throw fixture.failure;
      return {options: {allowBody: true, equipmentCatalog: structuredClone(fixture.catalog)}};
    },
    save: async (base, raw) => {
      fixture.saves.push(raw);
      revision = {...base, revid: base.revid + 1, raw};
      return {revision};
    }
  };
  fixture.session = site.create(adapter);
  await fixture.session.load();
  return fixture;
}

test('a retained effect can be saved after renaming, reordering or changes to other entities', async () => {
  const f = await open();
  f.session.editor.edit(key, '脚注');
  f.catalog.sample.talents[0].name = '新名称';
  f.catalog.sample.talents.reverse();
  f.catalog.unrelated = {template: '品牌套装信息', title: '无关样本'};
  await f.session.save();
  assert.equal(f.session.status, 'VERIFIED');
  assert.equal(f.saves.length, 1);
  assert.match(f.session.editor.rules[key].label, /新名称/);
  assert.equal(f.session.state.fields[key].value, '脚注');
  assert.equal(f.reads, 2);
});

test('removed, replaced or moved keys keep the draft and require a fresh load', async () => {
  const changes = [
    c => c.sample.talents.shift(),
    c => {c.sample.talents[0].id = 'replacement';},
    c => {c.sample.talents[0].mode = 'PVP';},
    c => {c.sample.template = '装备组信息';},
    c => {delete c.sample;}
  ];
  for (const change of changes) {
    const f = await open();
    f.session.editor.edit(key, '手稿');
    f.session.setSummary('摘要');
    change(f.catalog);
    await assert.rejects(f.session.save(), /可编辑字段已更新/);
    assert.equal(f.saves.length, 0);
    assert.equal(f.session.needsReload, true);
    assert.equal(f.session.state.fields[key].value, '手稿');
    assert.equal(f.session.summary, '摘要');
    await assert.rejects(f.session.save(), /RELOAD_REQUIRED/);
    if (f.catalog.sample?.template === entity.template) {
      await f.session.load();
      assert.equal(f.session.needsReload, false);
      assert.equal(f.session.editor.rules[key], undefined);
    }
  }
});

test('a failed catalog read leaves the draft retryable without a write', async () => {
  const f = await open();
  f.session.editor.edit(key, '暂存');
  f.failure = new Error('读取失败');
  await assert.rejects(f.session.save(), /读取失败/);
  assert.equal(f.saves.length, 0);
  assert.equal(f.session.state.fields[key].value, '暂存');
  delete f.failure;
  await f.session.save();
  assert.equal(f.saves.length, 1);
});

test('restoring absent, explicitly empty and nonempty notes preserves exact bytes without a write', async () => {
  for (const field of [key, '其他机制']) {
    for (const [source, restored, presence] of [
      ['', '', 'missing'], ['\n|' + field + '=  ', '', 'empty'], ['\n|' + field + '=  原文 ', '原文', 'value']
    ]) {
      const f = await open(source);
      const base = f.session.base.raw;
      f.session.editor.edit(field, '暂存');
      f.session.editor.edit(field, restored);
      assert.equal(f.session.state.fields[field].presence, presence);
      assert.equal(f.session.contentDirty, false);
      assert.equal(f.session.preview(), base);
      await f.session.save();
      assert.equal(f.saves.length, 0);
      assert.equal(f.reads, 1);
    }
    const f = await open('\n|' + field + '=原文');
    f.session.editor.edit(field, '');
    assert.equal(f.session.contentDirty, true);
    await f.session.save();
    assert.equal(f.saves.length, 1);
    assert.equal(f.session.state.fields[field].presence, 'empty');
  }
});
