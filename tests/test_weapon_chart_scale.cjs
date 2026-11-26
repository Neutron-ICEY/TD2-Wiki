'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const reader = fs.readFileSync(path.join(__dirname, '../ui/brand-sets/brand-sets.js'), 'utf8');
const scale = reader.slice(reader.indexOf('var weaponGridCm'), reader.indexOf('function mountWeaponAxes'));
const chooseSpan = vm.runInNewContext(scale + '\nweaponChartSpan');
const catalog = require('../data/equipment/weapon-charts.json');

test('half-cell clearance triggers the next linear tier, including exact equality', () => {
  for (const current of [200, 250, 300, 400, 2750]) {
    const side = current / 2 - 12.5, top = current - 12.5;
    for (const [delta, next] of [[-.001, current], [0, current + 50], [.001, current + 50]]) {
      assert.equal(chooseSpan(side + delta, side + delta, false), next);
      assert.equal(chooseSpan(side + delta, 0, true), next);
      assert.equal(chooseSpan(0, top + delta, true), next);
    }
  }
  assert.equal(chooseSpan(0, 0, false), 200);
  assert.equal(chooseSpan(0, 0, true), 200);
});

test('all catalog stances and displayed traces fit the smallest aligned square', () => {
  function check(horizontal, up, bottomOrigin) {
    const span = chooseSpan(horizontal, up, bottomOrigin);
    const clearance = side => Math.min(side / 2 - horizontal, side / (bottomOrigin ? 1 : 2) - up);
    assert.equal((span / 2) % 25, 0);
    assert.ok(clearance(span) > 12.5);
    assert.ok(span >= 200 && (span === 200 || clearance(span - 50) <= 12.5));
  }
  for (const model of Object.values(catalog.models)) {
    for (const angles of Object.values(model.angles || {})) {
      const radius = Math.tan(Math.max(...angles) * Math.PI / 180) * catalog.distanceM * 100;
      check(radius, radius, false);
    }
  }
  for (const trace of Object.values(catalog.traces)) {
    let horizontal = 0, up = 0;
    const paths = trace.shots > 1 ? [...trace.groups, trace.path] : trace.groups;
    for (const points of paths) {
      for (const pair of points.split(' ')) {
        const [x, y] = pair.split(',').map(Number);
        assert.ok(y <= 0, 'a visible point falls below the bottom origin');
        horizontal = Math.max(horizontal, Math.abs(x));
        up = Math.max(up, -y);
      }
    }
    check(horizontal, up, true);
  }
});

test('zoom eases the projected scale, can reverse mid-flight and honors reduced motion', () => {
  const {document} = require('./editor-dom.cjs').create();
  document.createElementNS = (_, tag) => document.createElement(tag);
  const section = document.createElement('figure');
  section.isConnected = true;
  function append(parent, tag, className = '') {
    const node = document.createElement(tag);
    node.className = className;
    parent.append(node);
    return node;
  }
  const stage = append(section, 'div', 'recoil-stage');
  stage.getBoundingClientRect = () => ({width:460, height:460});
  const chart = append(stage, 'svg'), field = append(chart, 'svg');
  append(field, 'g', 'grid');
  append(field, 'path', 'axes');
  append(chart, 'g', 'ticks');

  let time = 0, serial = 0, dataProgress;
  const motion = {matches:false}, pending = new Map();
  const easing = reader.slice(reader.indexOf('function chartProgress'), reader.indexOf('/* Vision comparison'));
  const axes = reader.slice(reader.indexOf('function attributes('), reader.indexOf('function mountAccuracy'));
  const mount = vm.runInNewContext(easing + axes + '\nmountWeaponAxes', {
    document, window:{matchMedia:() => motion}, performance:{now:() => time},
    ResizeObserver:class { observe() {} },
    requestAnimationFrame:callback => { pending.set(++serial, callback); return serial; },
    cancelAnimationFrame:id => pending.delete(id)
  });
  const show = mount(section, false);
  const paint = fraction => { dataProgress = fraction; };
  const span = () => Number(field.getAttribute('viewBox').split(' ')[2]);
  function advance(to) {
    assert.equal(pending.size, 1);
    const [[id, callback]] = pending;
    pending.delete(id);
    time = to;
    callback(time);
  }
  const near = (value, expected) => assert.ok(Math.abs(value - expected) < 0.00001);

  show(180, 180, paint);
  assert.equal(span(), 200);
  advance(60);
  near(200 / span(), 1 - 0.5 * 0.129162);
  advance(120);
  near(span(), 800 / 3);
  near(dataProgress, 1 / 3);
  const interrupted = span();
  show(0, 0, paint);
  assert.equal(span(), interrupted);
  assert.equal(dataProgress, 0);
  advance(240);
  near(1 / span(), (1 / interrupted + 1 / 200) / 2);
  advance(360);
  assert.equal(span(), 200);
  assert.equal(dataProgress, 1);
  assert.equal(pending.size, 0);

  motion.matches = true;
  show(180, 180, paint);
  assert.equal(span(), 400);
  assert.equal(dataProgress, 1);
  assert.equal(pending.size, 0);
});
