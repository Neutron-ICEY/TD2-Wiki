const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const identity = require('../tools/identity.cjs');

test('each catalog read shares its lookup tables and the next read sees the new addresses and receipts', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'td2-identity-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const publishing = path.join(root, 'publishing');
  fs.mkdirSync(publishing);
  fs.mkdirSync(path.join(root, 'assets'));
  const asset = {kind: 'assets', id: 'sample', title: 'File:Old.png', source: 'assets/original.png'};
  const registry = path.join(publishing, 'registry.json');
  const baseline = path.join(publishing, 'baseline.json');
  const save = (file, rows) => fs.writeFileSync(file, JSON.stringify({entries: rows}));
  fs.writeFileSync(path.join(root, asset.source), '');
  save(registry, [asset]);
  save(baseline, []);

  const counts = new Map();
  const read = fs.readFileSync;
  t.mock.method(fs, 'readFileSync', function(file, ...args) {
    counts.set(file, (counts.get(file) || 0) + 1);
    return read.call(this, file, ...args);
  });
  const inputs = [{asset_ref: 'sample'}, {nested: {asset_ref: 'sample'}}];
  const before = identity.read(root, 'catalog.json', inputs);
  assert.deepEqual(before[0], {wiki_file: 'Old.png', confirmed_on_wiki: false, local_available: true});
  assert.deepEqual(before[1].nested, before[0]);
  assert.equal(counts.get(registry), 1);
  assert.equal(counts.get(baseline), 1);
  asset.title = 'File:New.png';
  save(registry, [asset]);
  save(baseline, [{namespace: 6, title: '文件:New.png'}]);
  const after = identity.read(root, 'catalog.json', inputs);
  assert.deepEqual(after[0], {wiki_file: 'New.png', confirmed_on_wiki: true, local_available: true});
  assert.deepEqual(after[1].nested, after[0]);
  assert.equal(counts.get(registry), 2);
  assert.equal(counts.get(baseline), 2);
  save(registry, [asset, asset]);
  assert.throws(() => identity.read(root, 'catalog.json', inputs), /ASSET_IDENTITY_NOT_UNIQUE/);
});
