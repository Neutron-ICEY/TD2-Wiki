'use strict';

const { execFileSync } = require('node:child_process');
const path = require('node:path');
const test = require('node:test');
const config = require('../publishing/reader-editor-production.json');

test('the entire registered Reader Gadget parses as an ECMAScript 5 script', () => {
  const reader = config.resource_naming.reader.find(row => row.title === 'Gadget:TD2Reader.js');
  const filename = path.resolve(__dirname, '..', reader.source);
  // Node bundles Acorn. The subprocess exposes it for this grammar check only.
  const check = [
    "const { readFileSync } = require('node:fs');",
    "const acorn = require('internal/deps/acorn/acorn/dist/acorn');",
    "acorn.parse(readFileSync(process.argv[1], 'utf8'), { ecmaVersion: 5, sourceType: 'script' });"
  ].join('\n');
  execFileSync(process.execPath, ['--expose-internals', '-e', check, filename]);
});
